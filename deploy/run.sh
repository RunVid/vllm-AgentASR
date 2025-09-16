#!/bin/bash
set -e

# Find the directory where the script is located, so it can be run from anywhere.
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
# Go to the parent directory where api.py is located
cd "$SCRIPT_DIR/.."

# This function runs a single server instance in an infinite loop.
# If the python process crashes, the loop will restart it automatically.
run_server() {
    local gpu_id=$1
    local port=$2
    
    # Assign GPU and Port for this instance
    export CUDA_VISIBLE_DEVICES=$gpu_id
    export PORT=$port
    
    # [FIX] Assign a unique cache directory for each vLLM instance using the
    # correct `VLLM_CACHE_ROOT` environment variable. This prevents race
    # conditions during torch.compile caching.
    export VLLM_CACHE_ROOT="/root/.cache/vllm_gpu_${gpu_id}"

    while true; do
        echo "[$(date)] - Starting server on GPU $gpu_id at port $port"
        
        # Run the server. If it crashes, the loop will continue.
        python3 api.py
        
        echo "[$(date)] - FATAL: Server on GPU $gpu_id crashed with exit code $?. Respawning in 5 seconds..."
        sleep 5
    done
}

# Define the specific GPUs to use
GPUS_TO_USE=(4 5 6 7)
NUM_GPUS=${#GPUS_TO_USE[@]}

if [ $NUM_GPUS -eq 0 ]; then
    echo "No GPUs specified in GPUS_TO_USE. Exiting."
    exit 1
fi

echo "Using $NUM_GPUS GPUs: ${GPUS_TO_USE[*]}. Starting one monitored server per specified GPU."

# Create a directory for log files and a single log file for all servers.
mkdir -p logs
LOG_FILE="logs/all_servers.log"
# Clear the log file on start to avoid confusion with logs from previous runs.
> "$LOG_FILE"
echo "All server logs will be appended to: $LOG_FILE"

BASE_PORT=51000
NGINX_UPSTREAM_CONFIG=""
port_offset=0

for gpu_id in "${GPUS_TO_USE[@]}"
do
    port=$((BASE_PORT + port_offset))
    echo "Launching monitor for server on GPU $gpu_id at port $port"

    # Add server to Nginx upstream config, ensuring a proper newline.
    NGINX_UPSTREAM_CONFIG+=$(printf "    server 127.0.0.1:%s;\\n" "$port")

    # Run the server monitor function in the background, appending its output to the shared log file
    run_server $gpu_id $port >> "$LOG_FILE" 2>&1 &

    port_offset=$((port_offset + 1))
done

echo "All server monitors have been started in the background."

# Generate the Nginx configuration file instead of printing it to the console.
CONFIG_FILE="$SCRIPT_DIR/vllm_load_balancer.conf"
echo ""
echo "================================================================"
echo "Nginx configuration file generated at:"
echo "  $CONFIG_FILE"
echo "================================================================"

cat > "$CONFIG_FILE" << EOF
upstream vllm_backend {
    # Round-robin load balancing
${NGINX_UPSTREAM_CONFIG}
}

server {
    # Listen on port 443 for HTTPS traffic
    listen 443 ssl;
    
    # IMPORTANT: Replace 'your_server_ip_or_domain' with your server's public IP address or domain name.
    server_name 8.34.125.71;

    # SSL Certificate configuration
    # For production, use a certificate from a trusted authority like Let's Encrypt.
    ssl_certificate /etc/nginx/ssl/self-signed.crt;
    ssl_certificate_key /etc/nginx/ssl/self-signed.key;

    location / {
        # --- API Key Authentication ---
        # All clients must provide a secret key in the 'X-API-Key' header.
        if (\$http_x_api_key != "6a033ce8d2c5346516741b9c38965e633b9a348d0999a31d957141e11d572f57") {
            return 401 'Unauthorized';
        }

        proxy_pass http://vllm_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Print the updated instructions for the user.
cat << EOF

================================================================
How to use this configuration:
================================================================
**IMPORTANT: For production use, obtain an SSL certificate from a trusted Certificate Authority (CA) like Let's Encrypt.**

1. Create a directory for SSL certificates and generate a self-signed certificate for testing:
   \`sudo mkdir -p /etc/nginx/ssl\`
   \`sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/ssl/self-signed.key -out /etc/nginx/ssl/self-signed.crt\`
   (You can press Enter for all the prompts to accept the defaults)

2. Install Nginx:
   \`sudo apt update && sudo apt install -y nginx\`

3. Copy the generated config file to Nginx's configuration directory:
   \`sudo cp "${CONFIG_FILE}" /etc/nginx/sites-available/vllm_load_balancer\`

4. Enable the new site by creating a symbolic link:
   \`sudo ln -s /etc/nginx/sites-available/vllm_load_balancer /etc/nginx/sites-enabled/\`

5. Test the Nginx configuration:
   \`sudo nginx -t\`

6. If the test is successful, reload Nginx to apply the changes:
   \`sudo systemctl reload nginx\`

7. **IMPORTANT**: Ensure that port 443 (for HTTPS) is open in your server's firewall.
   \`sudo ufw allow 443/tcp\`
   (You might want to close the old port: \`sudo ufw deny 8080/tcp\`)

8. Now, send your API requests from any client using HTTPS and the API key. Example with curl:
   \`curl -X POST -H "X-API-Key: 6a033ce8d2c5346516741b9c38965e633b9a348d0999a31d957141e11d572f57" --insecure -F "files=@/path/to/your/audio.wav" https://8.34.125.71/api/v1/offline_asr\`
   (The '--insecure' flag is needed to trust the self-signed certificate. Remove it when using a real certificate.)
================================================================

To stop all servers, run the following script:
  ./vllm-AgentASR/deploy/stop.sh
EOF


# Wait for all background processes to finish.
# The script will exit if you press Ctrl+C, which will also terminate the child processes.
wait
