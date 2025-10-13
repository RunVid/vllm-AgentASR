# SPDX-License-Identifier: Apache-2.0
import os, re
import time
import json
import struct
import asyncio
from io import BytesIO
from enum import Enum
from typing import List

from fastapi import FastAPI, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from typing_extensions import Annotated
import torchaudio
from vllm import LLM, SamplingParams
# from funasr.utils.postprocess_utils import rich_transcription_postprocess

os.environ["LOGURU_LEVEL"] = "DEBUG"

# 1. Load Model
MAX_AUDIO_FILES = 1
MODEL_PATH = os.getenv("MODEL_PATH", "/home/weiguo/workspace/checkpoints/checkpoint-AgentASR-V2-200000-merged")

print("Loading model...")
start_time = time.time()
llm = LLM(model=MODEL_PATH,
          max_model_len=4096,
          max_num_batched_tokens=4096,
          max_num_seqs=MAX_AUDIO_FILES,
          gpu_memory_utilization=0.2,
          limit_mm_per_prompt={"audio": MAX_AUDIO_FILES})
print(f"Model loaded in {time.time() - start_time:.2f}s")


# 2. Initialize FastAPI app
app = FastAPI()

# class Language(str, Enum):
#     auto = "auto"
#     zh = "zh"
#     en = "en"
#     yue = "yue"
#     ja = "ja"
#     ko = "ko"
#     nospeech = "nospeech"

regex = r"<\|.*\|>"

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <meta charset=utf-8>
            <title>Api information</title>
        </head>
        <body>
            <a href='./docs'>Documents of API</a>
        </body>
    </html>
    """

def generate_prompt():
    prompt = (
        "<|im_start|>system\nYou are a helpful assistant. /no_think<|im_end|>\n"
        "<|im_start|>user\n"
        f"Analyze the audio. EMOTION_OFF EVENT_ON TRANSCRIPTION_ON Audio 1: <|AUDIO|><|im_end|>\n"
        "<|im_start|>assistant\n"
        "<think>\n\n</think>\n\n"
    )
    return prompt
    
@app.post("/api/v1/asr")
async def turn_audio_to_text(files: Annotated[List[bytes], File(description="wav or mp3 audios in 16KHz")], keys: Annotated[str, Form(description="name of each audio joined with comma")]):
    if len(files) > MAX_AUDIO_FILES:
        return JSONResponse(status_code=400, content={"error": f"Cannot process more than {MAX_AUDIO_FILES} files at once."})

    audios_with_sr = []
    total_duration = 0
    
    for file_bytes in files:
        file_io = BytesIO(file_bytes)
        try:
            waveform, sample_rate = torchaudio.load(file_io)
            waveform_np = waveform.mean(0).numpy()
            
            waveform_np = waveform_np[:30*sample_rate] #maximum 30s audio

            duration = len(waveform_np) / sample_rate
            total_duration += duration
            audios_with_sr.append((waveform_np, sample_rate))
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Failed to process audio file: {e}"})
        finally:
            file_io.close()
    
    if not audios_with_sr:
        return {"result": []}

    prompt = generate_prompt()
    
    sampling_params = SamplingParams(temperature=0.01, max_tokens=512, top_k=1, stop_token_ids=None)
    mm_data = {"audio": audios_with_sr}
    inputs = {"prompt": prompt, "multi_modal_data": mm_data}
    
    start_time_inference = time.time()
    outputs = llm.generate(inputs, sampling_params=sampling_params)
    transcribe_time_ms = (time.time() - start_time_inference) * 1000
    
    rtf = transcribe_time_ms / (total_duration * 1000) if total_duration > 0 else 0
    print(f"ASR Stats: Duration={total_duration:.2f}s, LLM_Generation_Time={transcribe_time_ms:.2f}ms, RTF={rtf:.4f}")
    
    if not outputs:
        return {"result": []}
    
    text = outputs[0].outputs[0].text
    
    if keys == "":
        key_list = ["wav_file_tmp_name"]
    else:
        key_list = keys.split(",")
    
    result = {
        "key": key_list[0],
        "raw_text": text,
        "clean_text": re.sub(regex, "", text, 0, re.MULTILINE),
        "text": text
    }

    return {"result": [result]}

def detect_audio_format(audio_data: bytes) -> str:
    """Detect audio format based on file header."""
    if audio_data.startswith(b'RIFF') and audio_data[8:12] == b'WAVE':
        return 'wav'
    elif audio_data.startswith(b'\xFF\xFB') or audio_data.startswith(b'ID3'):
        return 'mp3'
    else:
        return 'unknown'

def fix_wav_header(audio_data: bytes) -> bytes:
    """Fix WAV header with correct file size information."""
    header = audio_data[:44]
    audio_content = audio_data[44:]
    
    data_size = len(audio_content)
    file_size = data_size + 36
    
    new_header = bytearray(header)
    struct.pack_into('<I', new_header, 4, file_size)
    struct.pack_into('<I', new_header, 40, data_size)
    
    return bytes(new_header) + bytes(audio_content)

@app.websocket("/api/v1/asr_stream_upload")
async def websocket_audio_stream(websocket: WebSocket):
    await websocket.accept()
    
    try:
        audio_buffer = bytearray()
        
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                audio_buffer += message["bytes"]
            elif "text" in message:
                command = message["text"]
                window_size_seconds = None
                
                if command.startswith('{') and command.endswith('}'):
                    try:
                        cmd_obj = json.loads(command)
                        if cmd_obj.get("command") == "TRANSCRIBE":
                            window_size_seconds = cmd_obj.get("window_size")
                            command = "TRANSCRIBE"
                    except json.JSONDecodeError:
                        pass
                        
                if command == "TRANSCRIBE":
                    audio_format = detect_audio_format(audio_buffer)
                    
                    if audio_format == 'unknown':
                        await websocket.send_json({"error": "Unsupported audio format. Only WAV and MP3 are supported."})
                        print(f"Unsupported audio format. Only WAV and MP3 are supported.")
                        continue
                    
                    if audio_format == 'wav':
                        audio_buffer = fix_wav_header(audio_buffer)
                    
                    file_io = BytesIO(audio_buffer)
                    try:
                        waveform, sample_rate = torchaudio.load(file_io) 
                        waveform_np = waveform.mean(0).numpy() 
                        waveform_np = waveform_np[:30*sample_rate] # maximum 30s audio
                        
                        audio_duration = len(waveform_np) / sample_rate
                        
                        if window_size_seconds is not None and window_size_seconds > 0:
                            window_samples = int(window_size_seconds * sample_rate)
                            if len(waveform_np) > window_samples:
                                waveform_np = waveform_np[-window_samples:]
                                audio_duration = window_samples / sample_rate
                        
                        audios_with_sr = [(waveform_np, sample_rate)]

                        prompt = generate_prompt()
                        sampling_params = SamplingParams(temperature=0.01, max_tokens=512, top_k=1, stop_token_ids=None)
                        mm_data = {"audio": audios_with_sr}
                        inputs = {"prompt": prompt, "multi_modal_data": mm_data}

                        start_time = time.time()
                        outputs = llm.generate(inputs, sampling_params=sampling_params)
                        transcribe_time_ms = (time.time() - start_time) * 1000
                        rtf = transcribe_time_ms / (audio_duration * 1000) if audio_duration > 0 else 0
                        
                        print(f"WebSocket ASR Stats: Duration={audio_duration:.2f}s, Transcribe_Time={transcribe_time_ms:.2f}ms, RTF={rtf:.4f}")
                        
                        if not outputs:
                            await websocket.send_json({"result": []})
                        else:
                            text = outputs[0].outputs[0].text
                            result = {
                                "key": "websocket_stream",
                                "raw_text": text,
                                "clean_text": re.sub(regex, "", text, 0, re.MULTILINE),
                                "text": text
                            }
                            await websocket.send_json({"result": [result]})
                        
                    except Exception as e:
                        await websocket.send_json({"error": f"Failed to process audio: {str(e)}"})
                    finally:
                        file_io.close()
                        #audio_buffer = bytearray()
                
    except WebSocketDisconnect as e:
        client_host = websocket.client.host if hasattr(websocket, 'client') else 'unknown'
        client_port = websocket.client.port if hasattr(websocket, 'client') else 'unknown'
        user_agent = websocket.headers.get("user-agent", "unknown")
        print(f"Client disconnected - code: {e.code}, IP: {client_host}:{client_port}, User-Agent: {user_agent}")
    except Exception as e:
        try:
            await websocket.send_json({"error": f"Unexpected error: {str(e)}"})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 50002))
    uvicorn.run(app, host="0.0.0.0", port=port, ws='websockets')
