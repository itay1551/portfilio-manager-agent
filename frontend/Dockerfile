# Use Red Hat Universal Base Image 10 as the base image
FROM registry.access.redhat.com/ubi10/nginx-126

# The Red Hat nginx image serves application content from /opt/app-root/src.
# Place index.html in the same directory as this Dockerfile.
COPY index.html /opt/app-root/src/index.html

# The base image serves HTTP on a non-privileged port.
EXPOSE 8080

# Run nginx in the foreground.
CMD ["nginx", "-g", "daemon off;"]
