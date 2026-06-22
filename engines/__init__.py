ENGINE_REGISTRY = {}


def register(engine):
    ENGINE_REGISTRY[engine.name] = engine


def get_engine(name):
    return ENGINE_REGISTRY[name]


from engines import edge, say  # noqa: E402, F401

try:
    from engines import kokoro  # noqa: E402, F401
except ImportError:
    pass

try:
    from engines import kokoro_mlx  # noqa: E402, F401
except ImportError:
    pass

try:
    from engines import piper  # noqa: E402, F401
except ImportError:
    pass
