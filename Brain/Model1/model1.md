---

# 2. `Brain/model1/README.md` (Model A - Python)

Save this file as `SENTINEL/Brain/model1/README.md`.

```markdown
# Model A: Trust and Verification Engine (Python)

Model A operates in an isolated control zone. It processes sliding windows of worker behavior, validates commands against static constraints, scores temporal threat profiles, and issues write-authorization tokens.

## Technical Implementation

- **Language:** Python 3.10+
- **Frameworks:** PyTorch (Inference), FastAPI (Internal API Gateway), Uvicorn
- **Cryptographic Library:** `hashlib`, `hmac`
- **Core ML Architecture:** Bidirectional LSTM with 4-head self-attention.

## Directory Structure

```text
model1/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI application entry point
│   ├── config.py             # System thresholds and keys
│   ├── crypto.py             # HMAC token generation logic
│   └── engine.py             # PyTorch inference and scoring logic
├── models/
│   └── sentinel_lstm_v1.pth  # Pre-trained PyTorch weights
├── requirements.txt
└── README.md