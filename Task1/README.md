# Task1 — Повышение безопасности системы BionicPRO

## Цель

Повысить безопасность системы BionicPRO после инцидента с утечкой персональных данных и усилить архитектуру управления учётными данными пользователей.

Решение закрывает две части задания:

1. Архитектурное решение для управления учётными данными и безопасной работы с токенами.
2. Улучшение существующего приложения: замена обычного Authorization Code Grant на Authorization Code Flow with PKCE.

## Что реализовано

В рамках задания подготовлены:

- целевая архитектура управления доступом;
- диаграмма C4 в формате PlantUML;
- настройка PKCE для frontend-приложения;
- настройка PKCE для клиента `reports-frontend` в Keycloak;
- проверка, что frontend отправляет `code_challenge_method=S256`.

Файлы решения:

```text
Task1/
├── README.md
├── diagrams/
│   ├── bionicpro_security_to_be.puml
│   └── bionicpro_security_to_be.png
└── screenshots/
    └── pkce-auth-request.png
```

Также изменены:

```text
frontend/src/App.tsx
keycloak/realm-export.json
```

## Архитектурное решение

### 1. Унификация доступа

Для унификации доступа используется Keycloak в роли IAM Broker.

Keycloak выполняет функции:

- единой точки входа в систему BionicPRO;
- брокера для внешних удостоверяющих служб;
- центра управления ролями и группами;
- источника внутреннего идентификатора пользователя `internal_user_id`;
- поддержки PKCE для SPA-клиентов.

При этом Keycloak не становится основным хранилищем персональных и медицинских данных.

## 2. Внешние источники учётных записей

Для разных стран можно подключать разные внешние источники учётных записей:

- External IdP RU;
- External IdP EU;
- External IdP Other Countries.

Поддерживаемые варианты интеграции:

- OpenID Connect;
- SAML 2.0;
- LDAP / User Federation.

Такой подход позволяет хранить учётные записи пользователей в стране представительства и подключать разные удостоверяющие службы без изменения клиентских приложений BionicPRO.

## 3. Локальное хранение персональных и медицинских данных

Персональные и медицинские данные не переносятся в IAM-контур.

Они остаются в региональных хранилищах:

- Regional Medical DB RU;
- Regional Medical DB EU;
- другие региональные хранилища при выходе на новые рынки.

В IAM-контуре хранится только минимальная информация для авторизации:

- роли;
- группы;
- связи внешней учётной записи с `internal_user_id`;
- настройки realm и клиентов.

Связь между пользователем и медицинскими данными выполняется через внутренние идентификаторы, без передачи лишних персональных и медицинских данных в Keycloak.

## 4. Безопасная схема работы с токенами

Чтобы исключить передачу frontend-приложению токенов, полученных от внешнего IdP, в целевой архитектуре используется BFF / Token Mediator.

Frontend не получает:

- access token внешнего IdP;
- refresh token внешнего IdP;
- client secret;
- долгоживущие токены.

Frontend работает только через защищённую browser session:

- `HttpOnly cookie`;
- `Secure`;
- `SameSite`.

Токены хранятся на backend-стороне:

- в Token Vault / Session Store;
- в зашифрованном виде;
- с коротким TTL;
- с возможностью refresh token rotation.

## 5. Доступ к отчётам

Пользователь должен иметь доступ только к отчётам по своему протезу или своим протезам.

Для этого используется backend-проверка ownership:

```text
internal_user_id -> prosthesis_id
```

Даже если пользователь подменит идентификатор отчёта или протеза в запросе, backend должен проверить, что этот `prosthesis_id` принадлежит текущему пользователю.

## 6. Изменения во frontend

В `frontend/src/App.tsx` для `ReactKeycloakProvider` добавлены `initOptions`:

```tsx
const keycloakInitOptions: KeycloakInitOptions = {
  onLoad: 'login-required',
  pkceMethod: 'S256',
  checkLoginIframe: false,
};
```

И переданы в провайдер:

```tsx
<ReactKeycloakProvider
  authClient={keycloak}
  initOptions={keycloakInitOptions}
>
  <div className="App">
    <ReportPage />
  </div>
</ReactKeycloakProvider>
```

Это включает Authorization Code Flow with PKCE для SPA-приложения.

## 7. Изменения в Keycloak

Для клиента `reports-frontend` в `keycloak/realm-export.json` настроены параметры:

```json
{
  "clientId": "reports-frontend",
  "enabled": true,
  "publicClient": true,
  "standardFlowEnabled": true,
  "implicitFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "redirectUris": ["http://localhost:3000/*"],
  "webOrigins": ["http://localhost:3000"],
  "attributes": {
    "pkce.code.challenge.method": "S256"
  }
}
```

Смысл настроек:

- `publicClient: true` — frontend является публичным клиентом и не хранит client secret;
- `standardFlowEnabled: true` — используется Authorization Code Flow;
- `implicitFlowEnabled: false` — отключён устаревший implicit flow;
- `directAccessGrantsEnabled: false` — отключён password grant;
- `pkce.code.challenge.method: S256` — включён PKCE с SHA-256.

## 8. Проверка работы

Проект был запущен через Docker Compose.

Поднятые сервисы:

```text
frontend     -> http://localhost:3000
keycloak     -> http://localhost:8080
keycloak_db  -> localhost:5433
```

Пользователь успешно прошёл логин через Keycloak.

В DevTools → Network был проверен запрос:

```text
GET /realms/reports-realm/protocol/openid-connect/auth
```

В параметрах запроса присутствуют:

```text
code_challenge=...
code_challenge_method=S256
```

Это подтверждает, что PKCE включён и используется frontend-приложением.

Скрин проверки сохранён в:

```text
Task1/screenshots/pkce-auth-request.png
```

## 9. Важное замечание по `/reports`

После успешного логина frontend пытается вызвать:

```text
http://localhost:8000/reports
```

На момент выполнения Task1 backend-сервис отчётов ещё не был реализован и не был поднят в Docker Compose, поэтому браузер показывал ошибку подключения к `localhost:8000`.

Это не является ошибкой Task1.

Для Task1 проверяется:

- работа Keycloak;
- успешная аутентификация пользователя;
- включение PKCE;
- наличие `code_challenge_method=S256` в auth-запросе;
- архитектурное решение по безопасному управлению токенами.

Сервис `/reports` реализуется в следующем задании.

## 10. Итог

Решение повышает безопасность системы за счёт:

- перехода frontend-приложения на Authorization Code Flow with PKCE;
- отключения небезопасных OAuth flow для SPA;
- использования Keycloak как единой точки входа и IAM Broker;
- поддержки разных внешних IdP по странам;
- сохранения персональных и медицинских данных в региональных хранилищах;
- целевой схемы с BFF / Token Mediator, при которой frontend не получает токены внешнего IdP;
- backend-проверки доступа к отчётам по связке `internal_user_id -> prosthesis_id`.
