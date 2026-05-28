#!/bin/bash

cd frontend
podman build -t quay.io/aric-rosenbaum/neurosymbolic-ai/ui .

cd ..
cd orchestrator/src
pip freeze > requirements.txt
podman build -t quay.io/aric-rosenbaum/neurosymbolic-ai/orchestrator .

cd ../..
cd tools/portfolio/src
pip freeze > requirements.txt
podman build -t quay.io/aric-rosenbaum/neurosymbolic-ai/neurosymbolic-ai-portfolio .

cd ../../..
cd tools/value_at_risk/src
pip freeze > requirements.txt
podman build -t quay.io/aric-rosenbaum/neurosymbolic-ai/neurosymbolic-ai-risk .

cd ../../..
cd tools/guidelines/src
pip freeze > requirements.txt
podman build -t quay.io/aric-rosenbaum/neurosymbolic-ai/neurosymbolic-ai-guidelines .

