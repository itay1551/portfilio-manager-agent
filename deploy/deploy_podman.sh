#!/bin/bash

# Create a pod
podman pod create --name neurosymbolic-ai \
  -p 0.0.0.0:5000:5000 \
  -p 0.0.0.0:7001:7001 \
  -p 0.0.0.0:7002:7002 \
  -p 0.0.0.0:7003:7003

# Start your services inside the pod (use each app's *internal* port)
podman run -d --pod neurosymbolic-ai --name neurosymbolic-ai-var docker.io/aricrosenbaum/neurosymbolic-ai-var
podman run -d --pod neurosymbolic-ai --name neurosymbolic-ai-portfolio docker.io/aricrosenbaum/neurosymbolic-ai-portfolio
podman run -d --pod neurosymbolic-ai --name neurosymbolic-ai-guidelines docker.io/aricrosenbaum/neurosymbolic-ai-guidelines
podman run -d --pod neurosymbolic-ai --name neurosymbolic-ai-orchestrator docker.io/aricrosenbaum/neurosymbolic-ai-orchestrator