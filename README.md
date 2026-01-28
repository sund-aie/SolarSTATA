# SolarSTATA

AI-powered statistical analysis application with a Stata 19-like interface, built with Flask.

## Prerequisites

- Python 3.9 or higher
- [Ollama](https://ollama.com/) (optional, for AI-powered analysis features)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/sund-aie/SolarSTATA.git
cd SolarSTATA
```

2. Install the required Python packages:

```bash
pip install -r requirements.txt
```

3. (Optional) If you want AI-powered analysis, install Ollama and pull the LLaMA model:

```bash
ollama pull llama3.2
```

## Running the Application

Start the Flask server:

```bash
python3 app.py
```

The app will run at **http://127.0.0.1:5001**.

Open that URL in your browser to access the SolarSTATA interface.

> **Note for macOS users:** Port 5001 is used instead of the default 5000 to avoid conflicts with AirPlay Receiver, which occupies port 5000 on macOS Monterey and later.

## Features

- **Data Import** -- Upload CSV, Excel (.xlsx/.xls), Stata (.dta), and TSV/TXT files (up to 50 MB).
- **Descriptive Statistics** -- Summarize, tabulate, and explore your data.
- **Statistical Tests** -- T-tests, ANOVA, chi-square, correlation, regression (OLS, logistic, probit), non-parametric tests, survival analysis, and power analysis.
- **Stata-Style Command Line** -- Type commands like `summarize`, `regress`, `ttest`, and `tabulate` directly.
- **AI Analysis** -- Automated test selection and code generation via Ollama/LLaMA (requires Ollama running locally).
- **Literature Search** -- Search PubMed and CrossRef for related academic papers.

## Usage

1. Open the app in your browser at http://127.0.0.1:5001.
2. Upload a dataset using **File > Open**.
3. Use the GUI panels or the command line to run statistical tests.
4. (Optional) Use the AI assistant to get test recommendations and automated analysis.
