FROM python:3.11-alpine
WORKDIR /app
COPY relay_server.py .
EXPOSE 5000
CMD ["sh", "-c", "python relay_server.py --port ${PORT:-5000}"]
