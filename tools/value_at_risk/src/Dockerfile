# Use Red Hat Universal Base Image 10 minimal as the base image
FROM registry.access.redhat.com/ubi10/python-312-minimal

# Keep base lean and up to date
USER 0
RUN microdnf -y upgrade --setopt=install_weak_deps=0 && \
    microdnf -y install ca-certificates && \
    microdnf clean all

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir --only-binary=:all: \
        numpy scipy scikit-learn && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# App code
WORKDIR /app
COPY . /app

# Expose the port
EXPOSE 7001

# Use a non-root user if you like (UBI has 1001 by default)
USER 1001
CMD ["python", "app.py"]
