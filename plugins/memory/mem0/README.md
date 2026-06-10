# Mem0 Memory Provider



Server-side LLM fact extraction with semantic search, reranking, and automatic deduplication.



## Requirements



- `pip install mem0ai`

- Mem0 API key from [app.mem0.ai](https://app.mem0.ai)



## Setup



```bash

clawk memory setup    # select "mem0"

```



Or manually:

```bash

clawk config set memory.provider mem0

echo "MEM0_API_KEY=your-key" >> ~/.clawksis/.env

```



## Config



Config file: `$CLAWK_HOME/mem0.json`



| Key | Default | Description |

|-----|---------|-------------|

| `user_id` | `clawk-user` | User identifier on Mem0 |

| `agent_id` | `clawk` | Agent identifier |

| `rerank` | `true` | Enable reranking for recall |



## Tools



| Tool | Description |

|------|-------------|

| `mem0_profile` | All stored memories about the user |

| `mem0_search` | Semantic search with optional reranking |

| `mem0_conclude` | Store a fact verbatim (no LLM extraction) |

