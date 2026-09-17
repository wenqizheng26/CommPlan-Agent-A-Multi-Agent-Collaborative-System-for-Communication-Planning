# 运行依赖与许可

本项目无付费 API 或托管数据库依赖。许可证据来自固定上游版本和已安装包内的许可文件；完整 Python 版本及已复制的许可证文件路径见 `reports/environment.json`。

| 组件 | 固定版本 / revision | 许可 |
|---|---|---|
| Qwen/Qwen3-4B-GGUF，Q4_K_M | bc640142c66e1fdd12af0bd68f40445458f3869b | Apache-2.0 |
| BAAI/bge-small-zh-v1.5 | 7999e1d3359715c523056ef9478215996d62a620 | MIT |
| llama.cpp Windows Vulkan | b10950，ad6c66839 | MIT |
| Python | 3.12.14（当前基础运行时） | PSF |
| torch CPU | 2.8.0+cpu | BSD-3-Clause |
| transformers | 4.57.6 | Apache-2.0 |
| numpy | 2.2.6 | BSD，附带库各自许可证见包内通知 |
| xlrd | 2.0.2 | BSD |
| olefile | 0.47 | BSD |
| KaTeX | 0.18.7，前端 JS/CSS/字体全部本地提供 | MIT |

下载源、大小、SHA256 在 `runtime/assets_manifest.json`；下载脚本固定模型权重和推理程序的上游哈希。其他 Python 依赖详见 `requirements.lock.txt`，许可原文复制在 `runtime/licenses/python/`，原安装包也保留许可。

模型上游：[Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF)、[BGE](https://huggingface.co/BAAI/bge-small-zh-v1.5)、[llama.cpp](https://github.com/ggml-org/llama.cpp)。

数学排版采用 [KaTeX 本地部署方式](https://katex.org/docs/browser)，来自官方 npm 包 `katex@0.18.7`，下载包 SHA512 与 registry integrity 一致。逐文件 SHA256、下载 URL 与版本见 `web/assets/katex/manifest.json`，许可原文为同目录 `LICENSE`。运行时不访问 CDN。

原始用户工作簿不声明开源授权；仅在本地保留副本和定位。公式使用的 ITU/NASA/NIST 资料通过链接、条款位置与简短说明引用，未将其全文按项目许可证发布。

应用源代码和采用的模型/库使用开放许可证。当前宿主 Windows、显卡驱动和硬件属于现有系统环境，项目不重新许可这些产品；不需要额外购买 Excel 来运行或复算。
