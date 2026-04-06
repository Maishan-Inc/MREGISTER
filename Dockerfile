FROM node:22-bookworm-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json* ./
RUN npm install

COPY worker/requirements.txt ./worker/requirements.txt
RUN python3 -m pip install --break-system-packages -r worker/requirements.txt

COPY . .

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
