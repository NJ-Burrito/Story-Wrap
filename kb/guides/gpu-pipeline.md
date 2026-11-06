# GPU pipeline: tools, licences, VRAM, CPU-sparing flags

Hardware: RTX 2060 6 GB, i5-10400 (CLAUDE). Source: `research/09` sections 4 to 6, plus the 2026-10-22 licence pass. Nothing was downloaded or run in this pass; every VRAM statement is unverified on this machine.

## 1. Licence table (R-004 allowlist)

| Tool | Licence as read | Status | Grade |
|---|---|---|---|
| SDXL base 1.0 | CreativeML Open RAIL++-M (22 Jul 2023 text). Card says "intended for research purposes only"; LICENSE.md grants a royalty-free licence and allows hosting as a service, subject to Attachment A use restrictions (e.g. no medical advice, no fully automated decisions that harm legal rights). Attachment A not fully read | Allowed pending Q-02 | V https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md (summary fetch) |
| IP-Adapter SDXL (h94) | apache-2.0 metadata; no text read | Allowed | V https://huggingface.co/h94/IP-Adapter |
| xinsir controlnet-scribble-sdxl-1.0 | apache-2.0; fine-tuned from SDXL base, so the base's terms probably still apply [J] | Allowed | V https://huggingface.co/xinsir/controlnet-scribble-sdxl-1.0 |
| xinsir controlnet-lineart-sdxl-1.0 | unknown (HTTP 401 on fetch) | Not allowed until read | gap |
| Depth Anything V2 Small | apache-2.0 | Allowed | V https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf |
| Depth Anything V2 Base, Large | cc-by-nc-4.0 (non-commercial) | **Banned** | V https://huggingface.co/depth-anything/Depth-Anything-V2-Base-hf |
| RIFE (ECCV2022) | MIT per repo sidebar; LICENSE file not read | Allowed | S https://github.com/megvii-research/ECCV2022-RIFE |
| rife-ncnn-vulkan | MIT, copyright 2020 nihui (LICENSE read) | Allowed | V https://github.com/nihui/rife-ncnn-vulkan/blob/master/LICENSE |
| Real-ESRGAN | BSD-3-Clause per repo sidebar; pretrained weights' terms not stated on the page | Code allowed; weights Q-03 | S https://github.com/xinntao/Real-ESRGAN |
| Illustrious XL | fair-ai-public-license-1.0-sd; discourages monetisation; derivatives must be published openly; outputs not restricted | **Banned** (a LoRA on it inherits the terms) | V https://huggingface.co/OnomaAIResearch/Illustrious-xl-early-release-v0 |
| NoobAI-XL | Illustrious terms plus a stated commercial ban | **Banned** | S https://civarchive.com/articles/18619/what-the-license |
| MistoLine | conditional commercial use | Fallback only after reading | S research/09 |
| DAIN-Vulkan-GUI and similar | GPL-3.0 | Do not mix code into builds | S research/09 |

Record the base model and licence of every generated asset in its `meta.json` (R-004).

## 2. Chain (to test with one shot before any series work)

1. Ink line control: ControlNet scribble SDXL, black and white input, 768 px bucket (card says inputs resize to 1024 or equivalent bucket; thin lines follow input tightly) [V xinsir scribble card].
2. Identity: IP-Adapter SDXL with a fixed reference sheet. No training needed. VRAM unverified [S research/09].
3. Optional own style LoRA on our own ink drawings, trained on a clearly licensed base. Feasibility on 6 GB is unproven: kohya docs say 8 GB (10 GB recommended) and list levers (U-Net only, gradient checkpointing, cached latents and text-encoder outputs, 8-bit optimiser, network dim 4 to 8, bf16 or fp16 with `--no_half_vae`) [S https://www.mintlify.com/kohya-ss/sd-scripts/training/lora-sdxl]. One short test run, record peak VRAM (Q-04).
4. Upscale: Real-ESRGAN `RealESRGAN_x4plus_anime_6B` for ink and flat colour; `x4plus` for textured backgrounds [S research/09]. Generate at 768 px, upscale 2x to 4x, downscale to the 1080x1920 master, keep the large master as archive.
5. Depth: Depth Anything V2 Small (24.8M parameters [V https://github.com/DepthAnything/Depth-Anything-V2]) to drive parallax. Parallax tool not chosen (DepthFlow is an open-source parallax shader per PyPI [S https://pypi.org/project/depthflow]; licence unread, Q-07).
6. Frames: rife-ncnn-vulkan only where smooth motion is chosen (R-091); duplication otherwise.
7. Grade: undecided (Q-06). Delivery is SDR.
8. Encode: `h264_nvenc`, CUDA decode and `scale_cuda` so frames stay in video memory [S NVIDIA Video Codec SDK 13.0 FFmpeg guide, https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/ffmpeg-with-nvidia-gpu/index.html]. Check the build with `ffmpeg -encoders | grep nvenc` and `ffmpeg -h encoder=h264_nvenc`.

## 3. VRAM: what is and is not known

- SDXL on 6 GB: no official figure was found. diffusers documents CPU offload, VAE slicing and tiling, and calls sequential offload "extremely slow" [V https://huggingface.co/docs/diffusers/optimization/memory]. A third-party guide says 512 to 768 px on 6 GB [S https://eastondev.com/blog/en/posts/ai/20260721-comfyui-low-vram-acceleration/]. Treat 768 px as the planning value [J] and measure.
- Fit of IP-Adapter + ControlNet + SDXL together: unmeasured. First task of the animating stage's rehearsal: record peak VRAM (`nvidia-smi --query-gpu=memory.used --format=csv -l 1`).

## 4. ComfyUI flags (primary: `comfy/cli_args.py`)

| Flag | Use on this machine |
|---|---|
| `--reserve-vram N` | Yes, 1 to 2 GB reserve so the desktop does not cause out-of-memory (value unverified) |
| `--fp8_e4m3fn-unet` | Likely needed for SDXL weights; check quality on one ink shot |
| `--lowvram` | Do not rely on it; the source says it does nothing when dynamic VRAM is on |
| `--novram` | Last resort |
| `--cpu`, `--highvram` | Never |
| `--disable-dynamic-vram` | If dynamic loading misbehaves |
| `--use-sage-attention` | Test, no speed figure verified |

Source: https://github.com/comfyanonymous/ComfyUI/blob/master/comfy/cli_args.py [S via research/09]. Run `python main.py --help` on the install first.

## 5. CPU-sparing practice

- Decode with NVDEC (`-hwaccel cuda`), `-threads 2` on any CPU filter; this pattern measured fine for 4 reels [M research/10].
- One heavy job at a time on the GPU; cap parallel CPU jobs at 2 (R-006).
- Compositing and timeline are the only CPU work; do not run browser renders without Chrome GPU flags.
- No SD VAE tiling on the CPU path; no `--cpu`.

## 6. Gaps

Q-02 (SDXL Attachment A), Q-03 (Real-ESRGAN weights), Q-04 (LoRA on 6 GB), Q-06 (HDR-like grade), Q-07 (parallax tool licence), Q-09 (NVENC settings on this card).
