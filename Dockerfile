
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container at /app
COPY . .

# Make port 8000 available to the world outside this container
# (Often not strictly necessary for background bots like yours,
# but good practice for web apps)
EXPOSE 8000

# Run main.py when the container launches
# This is where your application starts
CMD ["python", "main.py"]