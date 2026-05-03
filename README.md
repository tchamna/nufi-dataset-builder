# nufi-dataset-builder

Standalone toolkit to build the **Nufi–French dictionary dataset** from the source **Excel workbook**: normalized **CSV** bundle and **`local-dictionary.sqlite`** for apps (e.g. African Online Dictionaries / Next.js `localDictionaryDb`).

Forked and packaged from the `dictionary-builder` pipeline in the African Online Dictionaries monorepo.

## Install

```bash
cd nufi-dataset-builder
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -e .
```

Requires **Python 3.11+**.

## CLI

Run from a project directory where you want `reports/` and `data/` created (defaults are relative to **current working directory**).

| Command | Description |
|---------|-------------|
| `nufi-dataset rebuild [--xlsx-path PATH] [--sheet MainDictionary] [--csv-dir …] [--db-path …]` | **Excel → CSV → SQLite** (full pipeline). |
| `nufi-dataset import-xlsx --xlsx PATH [--out-dir …] [--sheet …]` | **Excel → CSV only**. |
| `nufi-dataset from-csv [--csv-dir …] [--db-path …]` | **CSV → SQLite only**. |

### Workbook discovery (`rebuild` without `--xlsx-path`)

1. Environment variable **`NUFI_DICTIONARY_XLSX`**
2. **`./data/Dictionnaire_Nufi_Francais_Nufi_updated_2026.xlsx`**
3. First match when searching under the cwd (skips `.git`, `venv`, `node_modules`, …)
4. Optional **`G:/My Drive/.../Livres Nufi/...`** pattern when that drive exists

### Port check

`rebuild` refuses to run if something is listening on **3000** or **3001** (typical Next.js), to avoid SQLite locks. Use **`--allow-running-app`** to skip.

### Extra scripts (modules)

```bash
python -m nufi_dataset_builder.dump_bana_headword_audit --db data/local-dictionary.sqlite
python -m nufi_dataset_builder.migrate_add_orthography_category --db data/local-dictionary.sqlite
```

## Web UI (drag-and-drop)

```bash
nufi-dataset-web
```

Open **http://127.0.0.1:8765/** — drop an `.xlsx`, optional sheet name. Outputs use the same default paths relative to the **process working directory** (where you started the server).

Override host/port: **`NUFI_DATASET_HOST`**, **`NUFI_DATASET_PORT`**.

## Default outputs

| Artifact | Default path (relative to cwd) |
|----------|--------------------------------|
| CSV bundle | `reports/nufi-normalized-import/` |
| SQLite | `data/local-dictionary.sqlite` |

## Push to GitHub

1. Create an empty repo named **`nufi-dataset-builder`** on your account (no README/license if you will push this tree).

2. From this folder:

```bash
git init
git add .
git commit -m "Initial nufi-dataset-builder package"
git branch -M main
git remote add origin https://github.com/YOUR_USER/nufi-dataset-builder.git
git push -u origin main
```

Or with GitHub CLI:

```bash
gh repo create nufi-dataset-builder --public --source=. --remote=origin --push
```

Replace **`YOUR_USER`** with your GitHub username if using HTTPS.

## License

MIT — see [LICENSE](./LICENSE).
