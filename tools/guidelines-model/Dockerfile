FROM docker.io/seldonio/mlserver:1.7.1-sklearn AS builder

USER 0
COPY models/investment-guidelines-mlp.joblib /tmp/wrapped-model.joblib
COPY tools/guidelines-model/unwrap_model.py /tmp/unwrap_model.py
COPY tools/guidelines-model/model-settings.json /tmp/model-settings.json

RUN python /tmp/unwrap_model.py \
        /tmp/wrapped-model.joblib \
        /opt/mlserver/models/guidelines-mlp/investment-guidelines-mlp.joblib && \
    cp /tmp/model-settings.json /opt/mlserver/models/guidelines-mlp/model-settings.json && \
    rm -f /tmp/wrapped-model.joblib /tmp/unwrap_model.py /tmp/model-settings.json

FROM docker.io/seldonio/mlserver:1.7.1-sklearn

COPY --from=builder /opt/mlserver/models /opt/mlserver/models

ENV MLSERVER_MODELS_DIR=/opt/mlserver/models
