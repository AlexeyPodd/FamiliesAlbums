FROM python:3.9-bullseye
ENV PYTHONUNBUFFERED=1
WORKDIR /usr/src/familie_albums
COPY requirements.txt ./
RUN pip install cmake==3.25.0
RUN pip install -r requirements.txt
