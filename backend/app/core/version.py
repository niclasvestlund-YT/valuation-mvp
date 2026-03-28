import os

VERSION = "0.1.0"
BUILD_SHA = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA") or "local"
