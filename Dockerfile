FROM python:3.11-slim

WORKDIR /app

RUN pip install discord.py google-generativeai
RUN pip install --upgrade pip
