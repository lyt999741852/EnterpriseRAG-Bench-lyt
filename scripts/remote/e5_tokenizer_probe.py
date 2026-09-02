import argparse
import json
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--packages", action="store_true")
parser.add_argument("--config", action="store_true")
parser.add_argument("--load", action="store_true")
args = parser.parse_args()

MODEL = "/data06/embedding-models/multilingual-e5-large"

if args.packages:
    import transformers
    import tokenizers
    print("executable", sys.executable)
    print("transformers", transformers.__version__, transformers.__file__)
    print("tokenizers", tokenizers.__version__, tokenizers.__file__)

if args.config:
    with open(MODEL + "/config.json", encoding="utf-8") as handle:
        data = json.load(handle)
    print({key: data.get(key) for key in ("model_type", "architectures", "hidden_size", "max_position_embeddings", "vocab_size")})

if args.load:
    from transformers import AutoTokenizer
    print("BEFORE", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    print("AFTER", type(tokenizer).__name__, tokenizer.name_or_path, flush=True)
    print(tokenizer("query: hello", add_special_tokens=False)["input_ids"], flush=True)
