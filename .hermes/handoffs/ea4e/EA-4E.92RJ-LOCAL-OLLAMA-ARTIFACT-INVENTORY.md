# EA-4E.92RJ Local Ollama Artifact Inventory

Status: READ-ONLY FILE IDENTITY PASS / RUNTIME AND PRODUCTION HOLD.
Source baseline: `3ba57996fa8c76c51ae93defa6a9cd295a450d6e`.

The default local Ollama model manifest for `qwen3:14b` is present at
`%USERPROFILE%/.ollama/models/manifests/registry.ollama.ai/library/qwen3/14b`.
Its SHA-256 is
`bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`.
It declares schema version 2 and five blobs. Each blob's actual size and
SHA-256 matched the manifest on this read-only inspection:

| Blob | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| Config | 488 | `78b3b822087d5199783c8203553a5a92ce5eb7b683a5a81003f8efea9b399d74` |
| Model | 9276184896 | `a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e` |
| Template | 1723 | `ae370d884f108d16e7cc8fd5259ebc5773a0afa6e078b11f4ed7e39a27e0dfc4` |
| License | 11338 | `d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12` |
| Params | 120 | `cff3f395ef3756ab63e58b0ad1b32bb6f802905cae1472e6a12034e4246fbbdb` |

The local `C:/Users/David/AppData/Local/Programs/Ollama/ollama.exe` has
SHA-256 `ec9f3325f134597c7188b735dcc4e79a9eca4bf53f6b958ddf22aa04bf5ce57a`
and a valid Authenticode signature from Ollama Inc. No Ollama process was
observed; `OLLAMA_MODELS` was unset in the inspecting environment. These
observations do not establish the executable's runtime version, current
service endpoint, effective model selection, filesystem identity against
replacement, CPU-only operation, or receiver egress containment. Recheck
exact identities before any separately authorized execution.

No Ollama/OpenCode receiver or model was invoked. No GPU, ComfyUI, Docker
mutation, credential transfer, or production activation occurred. A model
file hash match is not a real agent handoff or production qualification.
The 92AT and production gates remain HOLD.
