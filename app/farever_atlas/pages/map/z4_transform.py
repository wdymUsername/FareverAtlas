"""Back-compat shim; prefer fow_layers.py."""

from .fow_layers import (  # noqa: F401
    FowLayerTransform as Z4Transform,
    load_fow_layers,
    save_fow_layers,
)


def load_z4_transform(path=None):
    return load_fow_layers(path)["Z4"].transform


def save_z4_transform(transform, path=None):
    layers = load_fow_layers(path)
    layers["Z4"].transform = transform
    return save_fow_layers(layers, path)
