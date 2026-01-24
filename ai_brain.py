import ollama
import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.formula.api import ols
import sys
import io

def clean_side_by_side_data(df_raw):
    """
    BRUTE FORCE CLEANING:
    - Forces extraction of exactly 8 groups.
    - Skips searching, just grabs columns 1-24 in chunks of 3.
    """
    try:
        dfs = []
        current_col = 1
        
        # Loop exactly 8 times for the 8 groups
        for group_num in range(1, 9): 
            # Safety check
            if current_col + 3 > len(df_raw.columns) + 1: 
                break
                
            # 1. Get Group Name (Handle "Unnamed")
            raw_name = str(df_raw.columns[current_col])
            if "Unnamed" in raw_name or raw_name == "nan":
                group_name = f"GROUP {group_num}"
            else:
                group_name = raw_name
            
            # 2. Get Data (Rows 1 onwards, 3 columns wide)
            chunk = df_raw.iloc[1:, current_col : current_col + 3].copy()
            
            # 3. Standardize Columns
            chunk.columns = ['TimeA', 'TimeB', 'TimeC']
            chunk['Group'] = group_name
            
            dfs.append(chunk)
            
            # Jump 3 columns
            current_col += 3
        
        if not dfs:
            return None
            
        clean_df = pd.concat(dfs, ignore_index=True)
        
        # Numeric Conversion
        for col in ['TimeA', 'TimeB', 'TimeC']:
            clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce')
            
        clean_df.dropna(subset=['TimeA'], inplace=True)
        
        return clean_df
    except Exception as e:
        print(f"Cleaning Error: {e}")
        return None

def analyze_data(dataframe, proposal_text):
    """
    1. CLEANS data (Brute Force).
    2. ANALYZES (Strict Imports).
    """
    code_to_run = "# Error in generation"
    captured_output = ""
    error_message = None

    try:
        # --- STEP 1: PRE-CLEAN ---
        clean_df = clean_side_by_side_data(dataframe)
        
        if clean_df is None or clean_df.empty:
            clean_df = dataframe.copy()
            data_status = "Raw (Cleaning Failed)"
        else:
            data_status = "Cleaned (8 Groups Forced)"

        data_sample = clean_df.head(5).to_string()

        # --- STEP 2: PROMPT ---
        # We explicitly tell it NOT to import things.
        
        part1 = f"""
        You are an Expert Biostatistician.
        
        --- INPUTS ---
        Status: {data_status}
        Data Sample: 
        {data_sample}
        
        --- MISSION ---
        The data is in `df` with columns: 'TimeA' (Baseline), 'TimeB' (Day 5), 'TimeC' (Day 10), 'Group'.
        """
        
        part2 = r"""
        CRITICAL RULE #1: NO NEW IMPORTS
        - The libraries `pandas`, `numpy`, `statsmodels.api as sm`, and `ols` are ALREADY imported.
        - DO NOT write `import statsmodels...`. USE EXISTING IMPORTS.

        CRITICAL RULE #2: DESCRIPTIVE STATS
        - Print the average hardness for each group:
          ```python
          print("\n=== DESCRIPTIVE STATISTICS (MEANS) ===")
          print(df.groupby('Group')[['TimeA', 'TimeB', 'TimeC']].mean())
          print("======================================\n")
          ```

        CRITICAL RULE #3: ANOVA LOOP
        - Run One-Way ANOVA for each time point.
        - Use this EXACT loop:
          ```python
          outcomes = {'TimeA': 'BASELINE', 'TimeB': 'DAY 5', 'TimeC': 'DAY 10'}
          
          for col, name in outcomes.items():
              print(f"\n==================================================")
              print(f" ANALYSIS FOR: {name}")
              print(f"==================================================")
              
              # Run ANOVA
              model = ols(f"{col} ~ C(Group)", data=df).fit()
              print(model.summary())
              
              # Summary
              pval = model.f_pvalue
              print(f"\nKEY FINDING: P-value = {pval:.4f}")
              if pval > 0.05:
                  print("CONCLUSION: No significant difference.")
              else:
                  print("CONCLUSION: Significant difference detected!")
          ```

        CRITICAL RULE #4: HUMAN SUMMARY
        - Print "--- HUMAN SUMMARY ---" and explain the results (Baseline vs Day 10).

        --- RULES ---
        - Return ONLY valid Python code inside a markdown block.
        """
        
        prompt = part1 + part2
        
        # --- STEP 3: CALL OLLAMA ---
        print("🧠 SolarStata is analyzing (Strict Mode)...")
        try:
            response = ollama.chat(model='llama3.2', messages=[
                {'role': 'user', 'content': prompt},
            ])
            ai_response = response['message']['content']
        except Exception as e:
            return {"generated_code": "", "stdout": f"Ollama Error: {e}", "error": str(e)}

        # --- STEP 4: CLEAN CODE ---
        if "```python" in ai_response:
            code_to_run = ai_response.split("```python")[1].split("```")[0]
        elif "```" in ai_response:
            code_to_run = ai_response.split("```")[1].split("```")[0]
        else:
            code_to_run = ai_response

        # --- STEP 5: EXECUTE ---
        # Force Imports AGAIN to be safe
        imports_header = """
import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.formula.api import ols
"""
        code_to_run = imports_header + code_to_run
        
        code_to_run = code_to_run.replace("markdown(", "print(")
        code_to_run = code_to_run.replace("display(", "print(")

        output_buffer = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = output_buffer
        
        try:
            local_env = {
                'pd': pd, 
                'np': np,            
                'print': print,
                'sm': sm,
                'ols': ols,
                'df': clean_df,
            }
            
            exec(code_to_run, local_env)
        except Exception as e:
            error_message = f"Execution Logic Failed: {e}"
        finally:
            captured_output = output_buffer.getvalue()
            sys.stdout = original_stdout

    except Exception as e:
        error_message = f"Critical System Error: {e}"

    return {
        "generated_code": code_to_run,
        "stdout": captured_output,
        "error": error_message
    }