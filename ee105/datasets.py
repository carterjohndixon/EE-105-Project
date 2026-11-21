"""Course datasets: MNIST handwritten digits without torchvision.

    images, labels = ee105.datasets.load_mnist("train")    # 60000 x 28 x 28 uint8, 60000 labels
    images, labels = ee105.datasets.load_mnist("test")     # 10000 test digits

Looks for the files in the kit's data/mnist folder first (the four files from
MNIST_ORG.zip, plain or .gz, or the zip itself), then in ~/.ee105/data/mnist,
and otherwise downloads them once (about 11 MB).
"""
import gzip
import os
import struct
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

KIT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("EE105_HOME", Path.home() / ".ee105")) / "data" / "mnist"
MIRRORS = ["https://ossci-datasets.s3.amazonaws.com/mnist/",
           "https://storage.googleapis.com/cvdf-datasets/mnist/"]
FILES = {"train": ("train-images-idx3-ubyte", "train-labels-idx1-ubyte"),
         "test": ("t10k-images-idx3-ubyte", "t10k-labels-idx1-ubyte")}


def _folders():
    out = []
    if os.environ.get("EE105_DATA"):
        out.append(Path(os.environ["EE105_DATA"]) / "mnist")
    out += [KIT / "data" / "mnist", CACHE, Path.cwd(), Path.cwd() / "data"]
    return out


def _variants(stem):
    dotted = stem.replace("-idx", ".idx")          # MNIST_ORG.zip spells them train-images.idx3-ubyte
    return [stem, stem + ".gz", dotted, dotted + ".gz"]


def _find(stem):
    for folder in _folders():
        for name in _variants(stem):
            p = folder / name
            if p.is_file():
                return p
        z = folder / "MNIST_ORG.zip"
        if z.is_file():
            with zipfile.ZipFile(z) as zf:
                for member in zf.namelist():
                    if Path(member).name in _variants(stem):
                        CACHE.mkdir(parents=True, exist_ok=True)
                        target = CACHE / Path(member).name
                        if not target.exists():
                            target.write_bytes(zf.read(member))
                        return target
    return None


def _download(stem):
    CACHE.mkdir(parents=True, exist_ok=True)
    last = None
    for base in MIRRORS:
        try:
            print(f"Downloading {stem}.gz ...", flush=True)
            with urllib.request.urlopen(base + stem + ".gz", timeout=60) as r:
                data = r.read()
            target = CACHE / (stem + ".gz")
            target.write_bytes(data)
            return target
        except Exception as e:      # try the next mirror
            last = e
    raise RuntimeError(f"Could not find or download {stem} ({last}). Put the four MNIST files "
                       f"(or MNIST_ORG.zip from the course page) in {KIT / 'data' / 'mnist'}.")


def _read(path):
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    magic = struct.unpack(">I", raw[:4])[0]
    ndim = magic & 0xFF
    dims = struct.unpack(">" + "I" * ndim, raw[4:4 + 4 * ndim])
    return np.frombuffer(raw, dtype=np.uint8, offset=4 + 4 * ndim).reshape(dims).copy()


def load_mnist(split="train"):
    """(images, labels) for split 'train' or 'test'. Images are uint8, 0 = black background."""
    img_stem, lab_stem = FILES[split]
    paths = [(_find(s) or _download(s)) for s in (img_stem, lab_stem)]
    return _read(paths[0]), _read(paths[1])
