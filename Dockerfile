# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file into the container at /app
# This step is important to ensure dependencies are installed.
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# This command installs Flask, arxiv, python-dotenv, and gunicorn inside the container.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container at /app
# This copies app.py, config.json, .env, and the templates folder.
COPY . .

# Expose the port that Flask will run on
# This tells Docker that the container will listen on port 8000.
EXPOSE 8000

# Run the Flask application
# This is the command that Docker will execute when the container starts.
# For local development, 'flask run' is used. For Railway, the Procfile will override this.
CMD ["flask", "run", "--host=0.0.0.0", "--port=8000"]
