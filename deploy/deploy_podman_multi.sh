#!/bin/bash

# Create a network so all teh containers can talk to each other
podman network create agentic-ai

# Create a pod per container image
podman run -d -p 7001:7001 --name neurosymbolic-ai-var --network ai-network docker.io/aricrosenbaum/neurosymbolic-ai-var
podman run -d -p 7002:7002 --name neurosymbolic-ai-portfolio --network ai-network docker.io/aricrosenbaum/neurosymbolic-ai-portfolio
podman run -d -p 7003:7003 --name neurosymbolic-ai-guidelines --network ai-network docker.io/aricrosenbaum/neurosymbolic-ai-guidelines
podman run -d -p 5000:5000 --name neurosymbolic-ai-orchestrator --network ai-network docker.io/aricrosenbaum/neurosymbolic-ai-orchestrator