#!/bin/bash
celery -A app.tasks.celery_app worker --beat --loglevel=info
