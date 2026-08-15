# Summary

Create a python script traverses folders and subfolders to find HTML files containing match reports (actas) and extracts 
relevant information from them. The extracted data should be saved in a structured JSON format.

# Description

Create a python script that:

- Traverse folder structure in `/src/actas-html/resources/` to find HTML files containing match reports (actas). 
- For each HTML file, extract relevant information such as season, category, group, phase, match ID, and any other relevant details.
- The extracted information must follow the JSON model definition in `/resources/actas-json/model-definition.json`. 
- The script should handle any variations in the HTML structure and ensure that the extracted data is accurate and complete.
- The extracted data should be saved in a structured JSON format into an equivalent folder structure in `/resources/actas-json/`, maintaining the same hierarchy as the original HTML files.

# Goal:

Create a python script into `/src/actas-html/` directory with the filename `parse_actas.py` that performs the above tasks.