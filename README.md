<img width="2000" height="2000" alt="Green Black Professional Minimal Fashion Brand Logo" src="https://github.com/user-attachments/assets/9d24593b-de05-4d45-9b64-a817df7e74fe" />


Integratr is a self-hosted AI backend. Your app is the screen. Integratr is the door behind it.

The Engine is built once. It gives every feature the same three things: one way to reach many AI models, a budget that can stop a call, and a log of what was spent. Features are Pipes. Chat, Agent, Image, Voice, and Search are Pipes. A custom Pipe uses the same plug.

LiteLLM does the model calls, the budgets, and the spend log. This repository is the thin shell in front of it: the plug a Pipe registers with.

## This repo

The Engine shell is here. The five Pipes are not built yet.

A Pipe never receives a provider key. It receives one virtual key, a model list, and a budget. Model calls go to the Engine. The Engine talks to LiteLLM.

Five names are allowed:

- `chat-default`
- `image-default`
- `embed-default`
- `speech-default`
- `transcribe-default`

You choose the real model behind each name, including DeepSeek or Moonshot. A Pipe only says the name.

## Run

Copy `.env.example` to `.env` and fill in the keys.

```bash
docker compose up --build
