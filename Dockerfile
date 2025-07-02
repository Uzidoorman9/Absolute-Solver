# Use official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Install dependencies
RUN pip install -r requirements.txt

# Set environment (optional, use Render instead ideally)
ENV PORT=8080

# Run the bot
CMD ["python", "main.py"]
