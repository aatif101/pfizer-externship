# M002 Secrets Manifest

## GEMINI_API_KEY

- **Service:** Google Gemini API
- **Dashboard URL:** https://aistudio.google.com/app/apikey
- **Format hint:** API key string provided by Google AI Studio. Do not commit or paste into source files.
- **Status:** pending
- **Destination:** local development environment or dotenv-managed runtime configuration used by the Streamlit app and CLI.
- **Obtain-key steps:**
  1. Open Google AI Studio with the Google account used for the demo.
  2. Create or select an API key for the Gemini API project.
  3. Store the key only through the project secret collection flow or local environment configuration.
  4. Verify the live provider path manually; automated tests must continue to use fake providers without this key.

## LANGFUSE_PUBLIC_KEY

- **Service:** Langfuse
- **Dashboard URL:** https://cloud.langfuse.com/
- **Format hint:** Public key value from a Langfuse project. Not sufficient alone for authentication, but still treat as configuration rather than source code.
- **Status:** pending
- **Destination:** local development environment or dotenv-managed runtime configuration used by optional tracing.
- **Obtain-key steps:**
  1. Open the Langfuse project settings for the demo workspace.
  2. Copy the project public key.
  3. Store it only through the project secret collection flow or local environment configuration.
  4. Confirm the app remains functional when the key is absent.

## LANGFUSE_SECRET_KEY

- **Service:** Langfuse
- **Dashboard URL:** https://cloud.langfuse.com/
- **Format hint:** Secret key value from a Langfuse project. Never print, log, or commit it.
- **Status:** pending
- **Destination:** local development environment or dotenv-managed runtime configuration used by optional tracing.
- **Obtain-key steps:**
  1. Open the Langfuse project settings for the demo workspace.
  2. Generate or copy the project secret key.
  3. Store it only through the project secret collection flow or local environment configuration.
  4. Verify tracing is optional and non-fatal when the key is missing or invalid.

## LANGFUSE_HOST

- **Service:** Langfuse
- **Dashboard URL:** https://cloud.langfuse.com/
- **Format hint:** URL such as `https://cloud.langfuse.com` or a self-hosted Langfuse base URL.
- **Status:** pending
- **Destination:** local development environment or dotenv-managed runtime configuration used by optional tracing.
- **Obtain-key steps:**
  1. Confirm whether the demo uses Langfuse Cloud or a self-hosted instance.
  2. Copy the base host URL from the Langfuse workspace or deployment.
  3. Store it only through the project secret collection flow or local environment configuration.
  4. Verify missing or unreachable Langfuse remains non-fatal for indexing, retrieval, and chat.
