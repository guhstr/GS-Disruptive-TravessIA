# Tecnologias utilizadas

## Aplicativo
React Native com Expo (SDK 58), TypeScript, React Navigation, Axios, AsyncStorage e expo-location para o GPS.

## Backend
Java 21 com Spring Boot 3.3 em microsserviços: gateway-service (porta 8080, autenticação JWT e controle de acesso), traffic-service (porta 8081, regras de negócio e banco de dados) e uma biblioteca comum. Usa Spring Security, Spring Cloud OpenFeign, Spring Data JPA, Flyway, Spring AI e banco de dados Oracle da FIAP.

## Serviço IoT e IA
Python 3 com FastAPI (porta 8083). Contém o módulo de comunicação MQTT (biblioteca paho-mqtt) e o assistente de dúvidas com RAG e memória de conversa.

## Dispositivo
ESP32 simulado no Wokwi, programado em C++ (Arduino) com as bibliotecas PubSubClient, ArduinoJson e LiquidCrystal_PCF8574.

## Inteligência artificial
Modelos do Google Gemini acessados por API: modelos de texto para as respostas do assistente, a orientação depois do pedido e o resumo para o gestor, e modelos de embedding (gemini-embedding-2) para a busca semântica do RAG.

## Comunicação
REST/JSON entre aplicativo e backend e entre os serviços; MQTT entre o serviço IoT e o ESP32, usando o broker público HiveMQ.
