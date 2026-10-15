"""`qa` service entrypoint (ECS Fargate): uvicorn ragcat.apps.qa:app"""

import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

from ragcat.apps.container import container
from ragcat.apps.http import create_app

app = create_app(container(), api=False, qa=True)
