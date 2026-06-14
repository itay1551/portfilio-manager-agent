FROM registry.access.redhat.com/ubi10/python-312-minimal

USER 0
RUN microdnf -y upgrade --setopt=install_weak_deps=0 && \
    microdnf -y install ca-certificates gcc-c++ python3.12-devel && \
    microdnf clean all

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    python -m spacy download en_core_web_lg && \
    microdnf -y remove gcc-c++ python3.12-devel && \
    microdnf clean all

WORKDIR /app
COPY app.py /app/

EXPOSE 8000

USER 1001
CMD ["python", "app.py"]
