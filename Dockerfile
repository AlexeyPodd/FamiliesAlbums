FROM python:3.9-bullseye
ENV PYTHONUNBUFFERED=1
WORKDIR /usr/src/family_albums
COPY ./ ./

RUN mkdir -p /usr/share/fonts/truetype/msttcorefonts/ && \
    install -m644 arialbd.ttf /usr/share/fonts/truetype/ && \
    mv ./arialbd.ttf /usr/share/fonts/truetype/msttcorefonts/

RUN pip install --upgrade pip && \
    pip install cmake==3.25.0 && \
    pip install -r requirements.txt

RUN adduser --disabled-password --no-create-home app
RUN chown -R app:app ./media && \
    chown -R app:app ./static && \
    chown -R app:app ./celerybeat && \
    chown -R app:app ./staticfiles && \
    chown -R app:app ./site_cache && \
    chmod -R 755 ./media && \
    chmod -R 755 ./static && \
    chmod -R 755 ./celerybeat && \
    chmod -R 755 ./staticfiles && \
    chmod -R 755 ./site_cache

USER app
