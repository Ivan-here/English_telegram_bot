"""Download the official Piper voice and its model card for offline synthesis."""

import hashlib
import shutil
import ssl
from pathlib import Path
from urllib.request import urlopen

import certifi

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/"
FILES = {
    "en_US-ljspeech-medium.onnx": "109d552e9dd78d92d1169a7edd6de38d",
    "en_US-ljspeech-medium.onnx.json": "0668112b8b3ac5bb4b12c2b1a366776a",
    "MODEL_CARD": "5ad31d314786587d4f97effb0b716d61",
}


def digest(path):
    checksum = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as data:
        for chunk in iter(lambda: data.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def main():
    destination = Path("models")
    destination.mkdir(parents=True, exist_ok=True)
    context = ssl.create_default_context(cafile=certifi.where())
    for name, expected in FILES.items():
        target = destination / name
        if target.is_file() and digest(target) == expected:
            continue
        temporary = target.with_name(name + ".part")
        print("Downloading " + name, flush=True)
        with urlopen(BASE + name, timeout=180, context=context) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if digest(temporary) != expected:
            raise ValueError("Piper download differs from the official voice manifest: " + name)
        temporary.replace(target)
    print("Piper assets verified and ready in models/", flush=True)


if __name__ == "__main__":
    main()
