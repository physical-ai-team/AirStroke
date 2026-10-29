from airstroke_shared.settings import env_float, env_int

DEBOUNCE_FRAMES = env_int("DEBOUNCE_FRAMES", 3)
ACTIVE_AREA = env_float("ACTIVE_AREA", 0.7)
CANVAS_ASPECT = env_int("CAMERA_WIDTH", 640) / env_int("CAMERA_HEIGHT", 480)
ONE_EURO_MIN_CUTOFF = env_float("ONE_EURO_MIN_CUTOFF", 1.0)
ONE_EURO_BETA = env_float("ONE_EURO_BETA", 0.007)
ONE_EURO_D_CUTOFF = env_float("ONE_EURO_D_CUTOFF", 1.0)
STATS_INTERVAL_SEC = env_float("STATS_INTERVAL_SEC", 5.0)
