FROM python:3.12-slim

COPY tests/requirements.txt /tmp/test-requirements.txt
COPY orchestrator/src/requirements.txt /tmp/orchestrator-requirements.txt

RUN pip install --no-cache-dir \
        -r /tmp/test-requirements.txt \
        -r /tmp/orchestrator-requirements.txt && \
    rm /tmp/test-requirements.txt /tmp/orchestrator-requirements.txt

WORKDIR /workspace
ENTRYPOINT ["pytest"]
