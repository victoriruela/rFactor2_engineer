# Jimmy Chat API — llama3.1-8B

Reference for the [chatjimmy.ai](https://chatjimmy.ai/) chat completion endpoint
using the **llama3.1-8B** model.

## Endpoint

```
POST https://chatjimmy.ai/api/chat
```

No authentication required. The API is publicly accessible.

## Required Headers

| Header         | Value                      |
|----------------|----------------------------|
| Content-Type   | `application/json`         |
| Accept         | `*/*`                      |
| Referer        | `https://chatjimmy.ai/`    |
| Origin         | `https://chatjimmy.ai`     |

The `Referer` and `Origin` headers are required — requests without them are
rejected.

## Request Body

```jsonc
{
  "messages": [
    { "role": "user", "content": "Your prompt here" }
  ],
  "chatOptions": {
    "selectedModel": "llama3.1-8B",
    "systemPrompt": "You are a helpful assistant.",
    "topK": 8,
    "temperature": 0.7          // optional
  },
  "attachment": null
}
```

### `messages`

Standard chat message array. Each message has `role` (`"user"` or
`"assistant"`) and `content` (string). Multi-turn conversations are supported
by providing the full history.

### `chatOptions`

| Field           | Type     | Required | Default        | Description                                                                                              |
|-----------------|----------|----------|----------------|----------------------------------------------------------------------------------------------------------|
| `selectedModel` | string   | yes      | —              | Model identifier. Use `"llama3.1-8B"`.                                                                   |
| `systemPrompt`  | string   | no       | `""`           | System-level instruction prepended to the conversation. Supports long prompts (tested up to ~4 000 chars). |
| `topK`          | number   | no       | `8`            | Top-K sampling. Lower values = more deterministic. `1` makes output nearly greedy.                       |
| `temperature`   | number   | no       | model default  | Sampling temperature. `0` = deterministic. Only sent when you need to override the default.               |

### `attachment`

Always `null`. The field must be present in the payload.

## Response

**Content-Type:** `text/plain`

The response body is the model's raw text output. It is **not** JSON — read it
with `response.text()`, not `response.json()`.

### Stats Tag

The model occasionally appends an XML-like stats block:

```
Your reply here<|stats|>{"tokens":42,"time":1.23}<|/stats|>
```

Strip it before using the reply:

```js
const raw = (await response.text()).replace(/<\|stats\|>(.+?)<\|\/stats\|>/s, "").trim();
```

### Wrapping Quotes

The model sometimes wraps the entire reply in double quotes. If the output
starts and ends with `"`, strip them:

```js
if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
  raw = raw.slice(1, -1).trim();
}
```

## Minimal Example (Node.js)

```js
const ENDPOINT = "https://chatjimmy.ai/api/chat";
const STATS_RE = /<\|stats\|>(.+?)<\|\/stats\|>/s;

async function chat(userMessage, systemPrompt = "") {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "*/*",
      Referer: "https://chatjimmy.ai/",
      Origin: "https://chatjimmy.ai",
    },
    body: JSON.stringify({
      messages: [{ role: "user", content: userMessage }],
      chatOptions: {
        selectedModel: "llama3.1-8B",
        systemPrompt,
        topK: 8,
      },
      attachment: null,
    }),
  });

  if (!res.ok) throw new Error(`Jimmy API ${res.status}`);

  let text = (await res.text()).replace(STATS_RE, "").trim();
  if (text.length >= 2 && text.startsWith('"') && text.endsWith('"')) {
    text = text.slice(1, -1).trim();
  }
  return text;
}
```

## Minimal Example (Python)

```python
import re, requests

ENDPOINT = "https://chatjimmy.ai/api/chat"
STATS_RE = re.compile(r"<\|stats\|>(.+?)<\|/stats\|>", re.DOTALL)

def chat(user_message: str, system_prompt: str = "") -> str:
    res = requests.post(
        ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Referer": "https://chatjimmy.ai/",
            "Origin": "https://chatjimmy.ai",
        },
        json={
            "messages": [{"role": "user", "content": user_message}],
            "chatOptions": {
                "selectedModel": "llama3.1-8B",
                "systemPrompt": system_prompt,
                "topK": 8,
            },
            "attachment": None,
        },
    )
    res.raise_for_status()
    text = STATS_RE.sub("", res.text).strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    return text
```

## Minimal Example (cURL)

```bash
curl -s https://chatjimmy.ai/api/chat \
  -H 'Content-Type: application/json' \
  -H 'Accept: */*' \
  -H 'Referer: https://chatjimmy.ai/' \
  -H 'Origin: https://chatjimmy.ai' \
  -d '{
    "messages": [{"role":"user","content":"Say hello"}],
    "chatOptions": {"selectedModel":"llama3.1-8B","systemPrompt":"","topK":8},
    "attachment": null
  }'
```

## Model Behavior Notes

Observations from ~2 000 API calls benchmarking `llama3.1-8B`:

- **Language:** Follows the system prompt language reliably. Spanish and
  Portuguese tested extensively.
- **System prompt adherence:** Prose-style instructions outperform numbered
  lists. The model follows positive instructions better than prohibitions.
- **Length control:** "Máximo 2-3 oraciones" / "Maximum 2-3 sentences" is
  respected most of the time. Occasional overruns happen; retry or truncate.
- **Common artifacts:** Rating echoes like `(5★)`, `(3/5)`, trailing meta
  commentary (`Nota: ...`), garbage tokens (`_goals`), sign-offs (`Atte,`).
  Post-processing cleanup is recommended.
- **Grammar quirks (Spanish):** Occasional first-person singular instead of
  plural (`agradezco` → should be `agradecemos`), misspelled conjugations
  (`Agradezcemos`), wrong verb forms (`Escríbanos` instead of `Escríbenos`).
  Regex-based post-processing handles these reliably.
- **Deterministic mode:** `temperature: 0` + `topK: 1` produces near-identical
  outputs for the same input. Useful for selection/classification tasks rather
  than creative generation.
- **Rate limiting:** No hard rate limit observed, but a ~250 ms delay between
  calls is recommended to avoid bursts.
- **Latency:** Typical response times are 1–4 seconds depending on output
  length.
- **Max output length:** Not formally documented. Outputs up to ~500 tokens
  observed without truncation.

## Error Handling

| Status | Meaning                | Action                         |
|--------|------------------------|--------------------------------|
| 200    | Success                | Parse response text            |
| 400    | Malformed request body | Check JSON structure           |
| 403    | Missing/wrong headers  | Verify Referer + Origin        |
| 500+   | Server error           | Retry after a short delay      |

The API does not return structured error JSON — error responses are plain text
or empty.
