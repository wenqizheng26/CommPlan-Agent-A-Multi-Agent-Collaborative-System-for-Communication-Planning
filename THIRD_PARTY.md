# 第三方资源与许可

本项目的 **Planning source Demo** 仅分发本仓库许可的应用源码、网页源码、登记公式 JSON 和用户文档；项目源码见 [LICENSE](LICENSE)。Python 包由用户运行 `setup_planning.cmd` 时依据 `requirements-planning.txt` 从包源安装，**不包含在 source ZIP 内**；各包的许可应查看相应安装包和上游项目。

| 资源 | 本地开发用途 | source Demo ZIP 是否包含 | 上游信息 |
| --- | --- | --- | --- |
| Qwen3-4B-GGUF Q4_K_M | 可选本地需求/计算建议/审查模型 | 否 | [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF)，本地模型目录附 Apache-2.0 `LICENSE` |
| llama.cpp b10950 Windows Vulkan | 可选本地模型服务 | 否 | [llama.cpp](https://github.com/ggml-org/llama.cpp)，本地资源目录附 MIT 与 LLVM OpenMP 通知 |
| BGE small zh v1.5 | 早期 Formula RAG 的可选嵌入模型，当前 Planning 使用词项检索 | 否 | [BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5)，本地模型目录附许可证 |
| Python 3.12 / Planning Python packages | 本机运行依赖 | 否 | 版本固定于 [requirements-planning.txt](requirements-planning.txt)，许可随所安装分发包提供 |

上述可选模型和推理库若被用户单独放入 `models/signal-formula-qwen3/`，必须保留随资源提供的许可证和来源信息。该目录被 `.gitignore` 排除，source Demo builder 也明确禁止它进入 ZIP。模型权重和 llama runtime 不得加入 Git 或推送到 GitHub。当前公开 README 和 source ZIP 不声称包含外部机器的 `runtime/assets_manifest.json`、`runtime/licenses/python/` 或已安装包清单。

公式卡的文献引用是链接、适用条件与短说明，不把 ITU、NASA、NIST 原文文档按项目 MIT 许可再分发。当前工作台不使用付费 API 或托管数据库。
