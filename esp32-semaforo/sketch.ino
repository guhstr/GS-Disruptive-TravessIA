/*
  Travessia Inteligente - semaforo simulado (ESP32 / Wokwi)

  Simulacao academica: nao controla semaforos reais.

  Ciclo de fases (nunca ha verde simultaneo para veiculos e pedestres):
    TODOS_VERMELHO -> VEICULOS_VERDE -> VEICULOS_AMARELO -> TODOS_VERMELHO
    -> PEDESTRE_VERDE (+ extensao) -> PEDESTRE_PISCANDO -> (reinicia)

  Um unico controlador simulado atende qualquer semaforo cadastrado: o ID vem do
  topico do comando e o nome vem no payload, e ambos aparecem no segundo LCD.

  MQTT (prefixo TOPICO_BASE):
    semaforo/<id>/comando     <- {"requestId","acao":"ESTENDER_TRAVESSIA","segundosExtras","semaforoNome"}
    semaforo/<id>/confirmacao -> {"requestId","status":"ACEITO|EXECUTADO|REJEITADO", ...}
    dispositivo/estado        -> {"online","bootId","fase","semaforoAtual",...} (retido, com LWT)
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_PCF8574.h>

// ---------------- Configuracao ----------------
const char *WIFI_SSID = "Wokwi-GUEST";
const char *WIFI_SENHA = "";
const char *MQTT_HOST = "broker.hivemq.com";
const uint16_t MQTT_PORTA = 1883;
const char *TOPICO_BASE = "fiap/gs2026/travessia";

const int PINO_VEIC_VERMELHO = 17;
const int PINO_VEIC_AMARELO = 16;
const int PINO_VEIC_VERDE = 4;
const int PINO_PED_VERMELHO = 26;
const int PINO_PED_VERDE = 27;
const int PINO_LCD_SDA = 23;
const int PINO_LCD_SCL = 22;
const int PINO_LCD2_SDA = 33;  // segundo barramento I2C (Wire1): LCD com o nome do semaforo
const int PINO_LCD2_SCL = 32;
const uint8_t ENDERECO_LCD = 0x27;

const unsigned long DURACAO_VEIC_VERDE_MS = 10000;
const unsigned long DURACAO_VEIC_AMARELO_MS = 3000;
const unsigned long DURACAO_TODOS_VERMELHO_MS = 2000;
// Tempo padrao de travessia do projeto: 15 s (verde fixo + verde piscando), mais o extra
// definido pelo backend (+5 s tempo seco, +10 s chuva).
const unsigned long TEMPO_TRAVESSIA_PADRAO_MS = 15000;
const unsigned long DURACAO_PED_PISCANDO_MS = 4000;
const unsigned long DURACAO_PED_VERDE_BASE_MS = TEMPO_TRAVESSIA_PADRAO_MS - DURACAO_PED_PISCANDO_MS;
const unsigned long INTERVALO_PISCA_MS = 500;
const int SEGUNDOS_EXTRAS_MAXIMO = 15;
const unsigned long INTERVALO_RECONEXAO_MS = 5000;
const unsigned long INTERVALO_ROLAGEM_MS = 400;

// ---------------- Estado ----------------
enum Fase {
  TODOS_VERMELHO,
  VEICULOS_VERDE,
  VEICULOS_AMARELO,
  TODOS_VERMELHO_PRE_PEDESTRE,
  PEDESTRE_VERDE,
  PEDESTRE_PISCANDO
};

const char *NOMES_FASE[] = {
  "TODOS_VERMELHO", "VEICULOS_VERDE", "VEICULOS_AMARELO",
  "TODOS_VERMELHO", "PEDESTRE_VERDE", "PEDESTRE_PISCANDO"
};

Fase faseAtual = TODOS_VERMELHO;
unsigned long inicioFaseMs = 0;
unsigned long duracaoFaseMs = DURACAO_TODOS_VERMELHO_MS;

int extensaoPendenteSeg = 0;
String requestIdPendente = "";
int semaforoPendenteId = 0;

int semaforoAtualId = 0;      // ultimo semaforo que pediu tempo extra
String semaforoAtualNome = "";
bool extensaoAplicadaNestaTravessia = false;

const int TAMANHO_HISTORICO = 8;
String historicoIds[TAMANHO_HISTORICO];
String historicoRespostas[TAMANHO_HISTORICO];
int historicoSemaforos[TAMANHO_HISTORICO];
int proximoHistorico = 0;

String bootId;
String topicoComandos, topicoEstado, prefixoSemaforo;

WiFiClient clienteWifi;
PubSubClient mqtt(clienteWifi);
unsigned long ultimaTentativaMs = 0;

LiquidCrystal_PCF8574 lcd(ENDERECO_LCD);          // contagem regressiva (Wire)
LiquidCrystal_PCF8574 lcdSemaforo(ENDERECO_LCD);  // semaforo atendido (Wire1)
String textoLcd[2];
String textoLcdSemaforo[2];
unsigned long ultimaRolagemMs = 0;
unsigned int posicaoRolagem = 0;

// ---------------- Saidas (LEDs) ----------------
struct Saidas {
  bool veicVermelho, veicAmarelo, veicVerde, pedVermelho, pedVerde;
};

void escreverSaidas(const Saidas &s) {
  // Regra de seguranca: se as duas luzes verdes forem pedidas juntas, tudo fica vermelho.
  if (s.veicVerde && s.pedVerde) {
    Serial.println("[SEGURANCA] conflito de verdes detectado; forcando todos vermelhos");
    Saidas seguro = {true, false, false, true, false};
    escreverSaidas(seguro);
    return;
  }
  digitalWrite(PINO_VEIC_VERMELHO, s.veicVermelho);
  digitalWrite(PINO_VEIC_AMARELO, s.veicAmarelo);
  digitalWrite(PINO_VEIC_VERDE, s.veicVerde);
  digitalWrite(PINO_PED_VERMELHO, s.pedVermelho);
  digitalWrite(PINO_PED_VERDE, s.pedVerde);
}

void atualizarLeds(unsigned long agora) {
  Saidas s = {true, false, false, true, false};
  switch (faseAtual) {
    case VEICULOS_VERDE:   s = {false, false, true, true, false}; break;
    case VEICULOS_AMARELO: s = {false, true, false, true, false}; break;
    case PEDESTRE_VERDE:   s = {true, false, false, false, true}; break;
    case PEDESTRE_PISCANDO: {
      bool aceso = ((agora - inicioFaseMs) / INTERVALO_PISCA_MS) % 2 == 0;
      s = {true, false, false, false, aceso};
      break;
    }
    default: break;
  }
  escreverSaidas(s);
}

// ---------------- Contagem regressiva (LCD) ----------------
Fase proximaFase(Fase fase) {
  switch (fase) {
    case TODOS_VERMELHO:              return VEICULOS_VERDE;
    case VEICULOS_VERDE:              return VEICULOS_AMARELO;
    case VEICULOS_AMARELO:            return TODOS_VERMELHO_PRE_PEDESTRE;
    case TODOS_VERMELHO_PRE_PEDESTRE: return PEDESTRE_VERDE;
    case PEDESTRE_VERDE:              return PEDESTRE_PISCANDO;
    default:                          return TODOS_VERMELHO;
  }
}

unsigned long duracaoPrevista(Fase fase) {
  switch (fase) {
    case VEICULOS_VERDE:    return DURACAO_VEIC_VERDE_MS;
    case VEICULOS_AMARELO:  return DURACAO_VEIC_AMARELO_MS;
    case PEDESTRE_VERDE:    return DURACAO_PED_VERDE_BASE_MS + (unsigned long)extensaoPendenteSeg * 1000UL;
    case PEDESTRE_PISCANDO: return DURACAO_PED_PISCANDO_MS;
    default:                return DURACAO_TODOS_VERMELHO_MS;
  }
}

// Tempo ate o inicio da fase alvo, somando as fases intermediarias.
unsigned long msAte(Fase alvo, unsigned long restanteAtual) {
  unsigned long total = restanteAtual;
  Fase f = proximaFase(faseAtual);
  while (f != alvo) {
    total += duracaoPrevista(f);
    f = proximaFase(f);
  }
  return total;
}

unsigned long emSegundos(unsigned long ms) {
  return (ms + 999UL) / 1000UL;
}

void escreverLinha(LiquidCrystal_PCF8574 &tela, String *cache, int linha, const char *texto) {
  char buffer[17];
  snprintf(buffer, sizeof(buffer), "%-16s", texto);
  if (cache[linha] == buffer) return;
  cache[linha] = buffer;
  tela.setCursor(0, linha);
  tela.print(buffer);
}

void escreverLinhaLcd(int linha, const char *texto) {
  escreverLinha(lcd, textoLcd, linha, texto);
}

void atualizarPainelSemaforo(unsigned long agora) {
  char linha[24];
  const char *conexao = mqtt.connected() ? " ON" : "OFF";
  if (semaforoAtualId == 0) {
    snprintf(linha, sizeof(linha), "Semaforo:    %s", conexao);
    escreverLinha(lcdSemaforo, textoLcdSemaforo, 0, linha);
    escreverLinha(lcdSemaforo, textoLcdSemaforo, 1, "aguardando app");
    return;
  }
  snprintf(linha, sizeof(linha), "Semaforo #%-3d%s", semaforoAtualId, conexao);
  escreverLinha(lcdSemaforo, textoLcdSemaforo, 0, linha);

  // Nomes com mais de 16 caracteres rolam horizontalmente.
  if (semaforoAtualNome.length() <= 16) {
    escreverLinha(lcdSemaforo, textoLcdSemaforo, 1, semaforoAtualNome.c_str());
    return;
  }
  if (agora - ultimaRolagemMs < INTERVALO_ROLAGEM_MS) return;
  ultimaRolagemMs = agora;
  String circular = semaforoAtualNome + "   ";
  posicaoRolagem = (posicaoRolagem + 1) % circular.length();
  String janela = (circular + circular).substring(posicaoRolagem, posicaoRolagem + 16);
  escreverLinha(lcdSemaforo, textoLcdSemaforo, 1, janela.c_str());
}

void atualizarContagem(unsigned long agora) {
  unsigned long decorrido = agora - inicioFaseMs;
  unsigned long restante = decorrido >= duracaoFaseMs ? 0 : duracaoFaseMs - decorrido;
  char linha[24];

  if (faseAtual == PEDESTRE_VERDE || faseAtual == PEDESTRE_PISCANDO) {
    unsigned long ms = faseAtual == PEDESTRE_VERDE ? restante + DURACAO_PED_PISCANDO_MS : restante;
    snprintf(linha, sizeof(linha), "Atravesse %3lus%s", emSegundos(ms),
             extensaoAplicadaNestaTravessia ? " +" : "");
  } else if (extensaoPendenteSeg > 0) {
    snprintf(linha, sizeof(linha), "Abre %2lus (+%ds)", emSegundos(msAte(PEDESTRE_VERDE, restante)),
             extensaoPendenteSeg);
  } else {
    snprintf(linha, sizeof(linha), "Ped. abre em%3lus", emSegundos(msAte(PEDESTRE_VERDE, restante)));
  }
  escreverLinhaLcd(0, linha);

  if (faseAtual == VEICULOS_VERDE || faseAtual == VEICULOS_AMARELO) {
    unsigned long ms = faseAtual == VEICULOS_VERDE ? restante + DURACAO_VEIC_AMARELO_MS : restante;
    snprintf(linha, sizeof(linha), "Veic. fecha %3lus", emSegundos(ms));
  } else {
    snprintf(linha, sizeof(linha), "Veic. abre  %3lus", emSegundos(msAte(VEICULOS_VERDE, restante)));
  }
  escreverLinhaLcd(1, linha);
}

// ---------------- MQTT: respostas ----------------
void publicarEstado() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["online"] = true;
  doc["bootId"] = bootId;
  doc["fase"] = NOMES_FASE[faseAtual];
  doc["extensaoPendente"] = extensaoPendenteSeg;
  doc["semaforoAtual"] = semaforoAtualId;
  // Relogio do ESP32: permite medir as fases no tempo da simulacao, que pode rodar mais devagar.
  doc["tempoMs"] = millis();
  // Quanto falta para o sinal de pedestres fechar (0 fora da travessia). O app mostra este valor,
  // assim a contagem do celular acompanha o relogio do ESP32 e o LCD.
  doc["travessiaRestanteMs"] = msRestantesTravessia();
  // Com o sinal de pedestres fechado, informa quanto falta para ele abrir (mesmo valor do LCD).
  if (faseAtual != PEDESTRE_VERDE && faseAtual != PEDESTRE_PISCANDO) {
    unsigned long decorrido = millis() - inicioFaseMs;
    unsigned long restanteFase = decorrido >= duracaoFaseMs ? 0 : duracaoFaseMs - decorrido;
    doc["aberturaPedestreMs"] = msAte(PEDESTRE_VERDE, restanteFase);
  }
  String json;
  serializeJson(doc, json);
  mqtt.publish(topicoEstado.c_str(), json.c_str(), true);
}

String topicoConfirmacao(int semaforoId) {
  return prefixoSemaforo + String(semaforoId) + "/confirmacao";
}

void lembrarResposta(const String &requestId, int semaforoId, const String &json) {
  for (int i = 0; i < TAMANHO_HISTORICO; i++) {
    if (historicoIds[i] == requestId) {
      historicoRespostas[i] = json;
      return;
    }
  }
  historicoIds[proximoHistorico] = requestId;
  historicoRespostas[proximoHistorico] = json;
  historicoSemaforos[proximoHistorico] = semaforoId;
  proximoHistorico = (proximoHistorico + 1) % TAMANHO_HISTORICO;
}

int indiceNoHistorico(const String &requestId) {
  for (int i = 0; i < TAMANHO_HISTORICO; i++) {
    if (historicoIds[i] == requestId) return i;
  }
  return -1;
}

// Tempo que ainda falta para fechar o sinal de pedestres (verde fixo + verde piscando).
unsigned long msRestantesTravessia() {
  unsigned long decorrido = millis() - inicioFaseMs;
  unsigned long restanteFase = decorrido >= duracaoFaseMs ? 0 : duracaoFaseMs - decorrido;
  if (faseAtual == PEDESTRE_VERDE) return restanteFase + DURACAO_PED_PISCANDO_MS;
  if (faseAtual == PEDESTRE_PISCANDO) return restanteFase;
  return 0;
}

void responder(int semaforoId, const String &requestId, const char *status, const char *detalheChave,
               const char *detalheValor, int segundosAplicados = -1) {
  if (strcmp(status, "REJEITADO") == 0) {
    Serial.printf("[SOLICITACAO] Pedido de mais tempo recusado: %s\r\n", detalheValor);
  }
  JsonDocument doc;
  doc["requestId"] = requestId;
  doc["status"] = status;
  doc["bootId"] = bootId;
  if (detalheChave) doc[detalheChave] = detalheValor;
  if (segundosAplicados >= 0) doc["segundosAplicados"] = segundosAplicados;
  // O app usa este valor para mostrar a contagem regressiva e avisar quando a travessia terminou.
  if (strcmp(status, "EXECUTADO") == 0) doc["travessiaRestanteMs"] = msRestantesTravessia();
  String json;
  serializeJson(doc, json);
  lembrarResposta(requestId, semaforoId, json);
  mqtt.publish(topicoConfirmacao(semaforoId).c_str(), json.c_str());
  Serial.printf("[MQTT] confirmacao -> %s\r\n", json.c_str());
}

// ---------------- Fases ----------------
void entrarFase(Fase nova, unsigned long agora) {
  faseAtual = nova;
  inicioFaseMs = agora;

  switch (nova) {
    case VEICULOS_VERDE:   duracaoFaseMs = DURACAO_VEIC_VERDE_MS; break;
    case VEICULOS_AMARELO: duracaoFaseMs = DURACAO_VEIC_AMARELO_MS; break;
    case PEDESTRE_PISCANDO: duracaoFaseMs = DURACAO_PED_PISCANDO_MS; break;
    case PEDESTRE_VERDE:
      duracaoFaseMs = DURACAO_PED_VERDE_BASE_MS;
      extensaoAplicadaNestaTravessia = false;
      if (extensaoPendenteSeg > 0) {
        duracaoFaseMs += (unsigned long)extensaoPendenteSeg * 1000UL;
        extensaoAplicadaNestaTravessia = true;
        Serial.printf("[SOLICITACAO] Tempo extra aplicado: travessia com %lu s (%lu s padrao + %d s extras)\r\n",
                      (TEMPO_TRAVESSIA_PADRAO_MS / 1000UL) + extensaoPendenteSeg,
                      TEMPO_TRAVESSIA_PADRAO_MS / 1000UL, extensaoPendenteSeg);
        responder(semaforoPendenteId, requestIdPendente, "EXECUTADO", nullptr, nullptr, extensaoPendenteSeg);
        extensaoPendenteSeg = 0;
        requestIdPendente = "";
      }
      break;
    default: duracaoFaseMs = DURACAO_TODOS_VERMELHO_MS; break;
  }

  Serial.printf("[FASE] %s por %lu ms\r\n", NOMES_FASE[nova], duracaoFaseMs);
  atualizarLeds(agora);
  publicarEstado();
}

void avancarFase(unsigned long agora) {
  switch (faseAtual) {
    case TODOS_VERMELHO:              entrarFase(VEICULOS_VERDE, agora); break;
    case VEICULOS_VERDE:              entrarFase(VEICULOS_AMARELO, agora); break;
    case VEICULOS_AMARELO:            entrarFase(TODOS_VERMELHO_PRE_PEDESTRE, agora); break;
    case TODOS_VERMELHO_PRE_PEDESTRE: entrarFase(PEDESTRE_VERDE, agora); break;
    case PEDESTRE_VERDE:              entrarFase(PEDESTRE_PISCANDO, agora); break;
    case PEDESTRE_PISCANDO:           entrarFase(TODOS_VERMELHO, agora); break;
  }
}

// ---------------- Comandos ----------------
void tratarComando(int semaforoId, const String &payload) {
  JsonDocument doc;
  if (deserializeJson(doc, payload)) {
    Serial.println("[COMANDO] JSON invalido descartado");
    return;
  }
  String requestId = doc["requestId"] | "";
  if (requestId.length() == 0 || requestId.length() > 64) {
    Serial.println("[COMANDO] requestId ausente ou invalido; descartado");
    return;
  }

  int anterior = indiceNoHistorico(requestId);
  if (anterior >= 0) {
    Serial.println("[COMANDO] requestId repetido; reenviando ultima resposta");
    mqtt.publish(topicoConfirmacao(historicoSemaforos[anterior]).c_str(), historicoRespostas[anterior].c_str());
    return;
  }

  String acao = doc["acao"] | "";
  int segundos = doc["segundosExtras"] | 0;
  String nome = doc["semaforoNome"] | "";

  semaforoAtualId = semaforoId;
  semaforoAtualNome = nome.length() > 0 ? nome : String("Semaforo ") + semaforoId;
  posicaoRolagem = 0;

  Serial.println("==================================================");
  Serial.printf("[SOLICITACAO] Semaforo #%d (%s)\r\n", semaforoId, semaforoAtualNome.c_str());
  Serial.printf("[SOLICITACAO] Pedestre pediu mais tempo pelo app: +%d s (fase atual: %s)\r\n",
                segundos, NOMES_FASE[faseAtual]);

  if (acao != "ESTENDER_TRAVESSIA") {
    responder(semaforoId, requestId, "REJEITADO", "motivo", "ACAO_DESCONHECIDA");
    return;
  }
  if (segundos < 1 || segundos > SEGUNDOS_EXTRAS_MAXIMO) {
    responder(semaforoId, requestId, "REJEITADO", "motivo", "SEGUNDOS_FORA_DO_LIMITE");
    return;
  }
  if (extensaoPendenteSeg > 0 || (faseAtual == PEDESTRE_VERDE && extensaoAplicadaNestaTravessia)) {
    responder(semaforoId, requestId, "REJEITADO", "motivo", "EXTENSAO_JA_PROGRAMADA");
    return;
  }

  if (faseAtual == PEDESTRE_VERDE) {
    duracaoFaseMs += (unsigned long)segundos * 1000UL;
    extensaoAplicadaNestaTravessia = true;
    Serial.printf("[SOLICITACAO] Travessia em andamento: +%d s (total %lu s = %lu s padrao + %d s extras)\r\n",
                  segundos, (TEMPO_TRAVESSIA_PADRAO_MS / 1000UL) + segundos,
                  TEMPO_TRAVESSIA_PADRAO_MS / 1000UL, segundos);
    responder(semaforoId, requestId, "ACEITO", "execucao", "IMEDIATA");
    responder(semaforoId, requestId, "EXECUTADO", nullptr, nullptr, segundos);
  } else {
    // Fora da fase de pedestre a extensao e agendada: o ciclo de veiculos nao e interrompido.
    extensaoPendenteSeg = segundos;
    requestIdPendente = requestId;
    semaforoPendenteId = semaforoId;
    Serial.printf("[SOLICITACAO] Sinal de pedestre fechado: +%d s agendado para a proxima travessia\r\n",
                  segundos);
    responder(semaforoId, requestId, "ACEITO", "execucao", "PROXIMA_TRAVESSIA");
  }
  Serial.println("==================================================");
  publicarEstado();
}

void aoReceberMensagem(char *topico, byte *conteudo, unsigned int tamanho) {
  String payload;
  payload.reserve(tamanho);
  for (unsigned int i = 0; i < tamanho; i++) payload += (char)conteudo[i];
  Serial.printf("[MQTT] %s <- %s\r\n", topico, payload.c_str());

  // Topico esperado: <prefixo>/semaforo/<id>/comando
  String t = topico;
  if (!t.startsWith(prefixoSemaforo) || !t.endsWith("/comando")) return;
  String trechoId = t.substring(prefixoSemaforo.length(), t.length() - String("/comando").length());
  int semaforoId = trechoId.toInt();
  if (semaforoId <= 0 || String(semaforoId) != trechoId) {
    Serial.println("[COMANDO] ID de semaforo invalido no topico; descartado");
    return;
  }
  tratarComando(semaforoId, payload);
}

// ---------------- Conectividade (nao bloqueante) ----------------
void manterConexao(unsigned long agora) {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  if (agora - ultimaTentativaMs < INTERVALO_RECONEXAO_MS) return;
  ultimaTentativaMs = agora;

  String clientId = "esp32-travessia-" + bootId;
  String lwt = "{\"online\":false,\"bootId\":\"" + bootId + "\"}";
  Serial.println("[MQTT] conectando ao broker...");
  if (mqtt.connect(clientId.c_str(), topicoEstado.c_str(), 1, true, lwt.c_str())) {
    mqtt.subscribe(topicoComandos.c_str(), 1);
    Serial.printf("[MQTT] conectado; ouvindo %s\r\n", topicoComandos.c_str());
    publicarEstado();
  } else {
    Serial.printf("[MQTT] falha (rc=%d); o semaforo segue o ciclo normal\r\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PINO_VEIC_VERMELHO, OUTPUT);
  pinMode(PINO_VEIC_AMARELO, OUTPUT);
  pinMode(PINO_VEIC_VERDE, OUTPUT);
  pinMode(PINO_PED_VERMELHO, OUTPUT);
  pinMode(PINO_PED_VERDE, OUTPUT);

  bootId = String(esp_random(), HEX);
  prefixoSemaforo = String(TOPICO_BASE) + "/semaforo/";
  topicoComandos = prefixoSemaforo + "+/comando";
  topicoEstado = String(TOPICO_BASE) + "/dispositivo/estado";

  Wire.begin(PINO_LCD_SDA, PINO_LCD_SCL);
  Wire1.begin(PINO_LCD2_SDA, PINO_LCD2_SCL);
  lcd.begin(16, 2, Wire);
  lcd.setBacklight(255);
  lcdSemaforo.begin(16, 2, Wire1);
  lcdSemaforo.setBacklight(255);

  Serial.printf("Travessia Inteligente - controlador simulado (boot %s)\r\n", bootId.c_str());
  entrarFase(TODOS_VERMELHO, millis());

  WiFi.begin(WIFI_SSID, WIFI_SENHA, 6);
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setCallback(aoReceberMensagem);
  mqtt.setBufferSize(512);
  // O simulador pode rodar bem mais devagar que o tempo real; com o keepalive padrao (15 s) o broker
  // chegava a considerar o ESP32 desconectado e publicava o LWT no meio de um comando.
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(30);
}

void loop() {
  unsigned long agora = millis();
  manterConexao(agora);
  mqtt.loop();

  if (agora - inicioFaseMs >= duracaoFaseMs) {
    avancarFase(agora);
  } else if (faseAtual == PEDESTRE_PISCANDO) {
    atualizarLeds(agora);
  }
  atualizarContagem(agora);
  atualizarPainelSemaforo(agora);

  // Durante a travessia, ou enquanto um tempo extra espera o sinal abrir, o estado e publicado
  // sempre que o numero da contagem muda no LCD, para o app mostrar o mesmo valor.
  static unsigned long ultimoSegundoPublicado = 0;
  bool pedestreAberto = faseAtual == PEDESTRE_VERDE || faseAtual == PEDESTRE_PISCANDO;
  if (pedestreAberto || extensaoPendenteSeg > 0) {
    unsigned long decorrido = agora - inicioFaseMs;
    unsigned long restanteFase = decorrido >= duracaoFaseMs ? 0 : duracaoFaseMs - decorrido;
    unsigned long segundoAtual = pedestreAberto ? emSegundos(msRestantesTravessia())
                                                : emSegundos(msAte(PEDESTRE_VERDE, restanteFase));
    if (segundoAtual != ultimoSegundoPublicado) {
      ultimoSegundoPublicado = segundoAtual;
      publicarEstado();
    }
  }
}
