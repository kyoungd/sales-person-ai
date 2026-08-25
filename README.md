# sales-person-ai

A minimal command-line sales assistant powered by the OpenAI Realtime API.

## Setup

```bash
npm install
```

## Run

```bash
export OPENAI_API_KEY="<your-api-key>"
npm start
```

Optional environment variables:
- `OPENAI_REALTIME_MODEL` (default: `gpt-4o-realtime-preview`)
- `SALES_PRODUCT_NAME` (default: `Sales Person AI`)

Type messages at the `you>` prompt. Type `exit` to quit.

## Test

```bash
npm test
```
