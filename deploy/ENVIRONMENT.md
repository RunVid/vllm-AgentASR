# Docker 部署环境要求

构建机器环境记录（2025-12-10），其他机器需满足相同或兼容的环境才能直接使用 Docker 镜像。

## 镜像信息

| 项目 | 值 |
|------|-----|
| 镜像名称 | `19pine/vllm-agent-asr` |
| 当前版本 | `0.0.0.dev` |
| 镜像大小 | ~55 GB |

## 目标机器要求

| 要求 | 说明 |
|------|------|
| **GPU** | NVIDIA GPU（建议同架构，如 RTX 5090/5080 等 Blackwell 架构） |
| **驱动** | ≥ 575.x（需支持 CUDA 12.9） |
| **nvidia-docker** | 安装 nvidia-container-toolkit |
| **Docker** | 任意支持 `--gpus` 参数的版本 |

## 快速部署

### 1. 拉取镜像

```bash
# 从 Docker Hub 拉取（推荐）
docker pull 19pine/vllm-agent-asr:0.0.0.dev

# 如果是私有镜像，先登录
docker login
docker pull 19pine/vllm-agent-asr:0.0.0.dev
```

### 2. 运行服务

```bash
# 方式一：使用部署脚本（推荐）
./deploy/docker-run.sh staging   # 测试环境
./deploy/docker-run.sh prod      # 生产环境

# 方式二：手动运行单个容器
docker run -d \
  --gpus device=0 \
  -e "MODEL_PATH=19pine/agentasr-v2.3-12400" \
  -e "HF_TOKEN=your_token_here" \
  -v "${HOME}/.cache/huggingface:/root/.cache/huggingface" \
  -p 50002:50002 \
  --ipc=host \
  19pine/vllm-agent-asr:0.0.0.dev
```

### 3. 验证服务

```bash
# 检查容器状态
docker ps | grep vllm-agent-asr

# 测试 API
curl http://localhost:50002/health
```

## 离线部署（可选）

如果目标机器无法访问 Docker Hub，可以使用离线方式：

```bash
# 在有网络的机器上导出
docker save -o vllm-agent-asr.tar 19pine/vllm-agent-asr:0.0.0.dev

# 传输到目标机器后加载
docker load -i vllm-agent-asr.tar
```

## 构建环境参考

以下是构建此镜像时的机器环境，供排查兼容性问题参考：

| 项目 | 值 |
|------|-----|
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 6.8.0-79-generic |
| GPU | NVIDIA GeForce RTX 5090 × 8 |
| Driver | 575.51.03 |
| CUDA | 12.9 |
| Docker | 27.5.1 |
| nvidia-container-cli | 1.17.8 |
