FROM python:3.9-bullseye
ENV PYTHONUNBUFFERED=1
WORKDIR /usr/src/familie_albums
COPY requirements.txt ./

COPY ./arialbd.ttf ./
RUN mkdir -p /usr/share/fonts/truetype/msttcorefonts/
RUN install -m644 arialbd.ttf /usr/share/fonts/truetype/
RUN mv ./arialbd.ttf /usr/share/fonts/truetype/msttcorefonts/

RUN pip install cmake==3.25.0
RUN pip install -r requirements.txt
