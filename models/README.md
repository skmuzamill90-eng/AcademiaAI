# Placement-status classifier

Train and evaluate the model using the labeled workbook:

```powershell
python scripts\train_placement_model.py "C:\Users\skmuz\Downloads\AcademiaAI_Student_Dataset_200_Records_Fixed_IDs.xlsx"
```

This creates `models/placement_status.joblib`. The FastAPI service loads that artifact for the placement prediction endpoint. If the artifact is missing or invalid, the API reports that the model is not ready instead of failing.

## What is trained

- Estimator: scikit-learn logistic regression with median imputation, standard scaling, and balanced class weights.
- Target: `placement_status == "Placed"` versus all other statuses.
- Evaluation: five-fold stratified cross-validation; every training student receives an out-of-fold estimate from a model that did not train on that student's row.
- Baseline: majority-class classifier.
- Reported metrics: precision, recall, F1, ROC-AUC, accuracy, and confusion matrix.
- Inputs: academic, attendance, LMS, and placement-readiness scores. Student ID, name, email, and `placement_status` are excluded from model features.
- Explanations: signed logistic-regression feature contributions, accompanied by each student's observed feature values.

The workbook has 200 records and only 29 positive (`Placed`) labels. These metrics are exploratory and will be statistically uncertain. The workbook has no placement outcome timestamps, so the model classifies the recorded placement status; it does **not** establish prediction of future placement. A stronger future-outcome model needs earlier dated features linked to later placement outcomes. Semester-performance, backlog-clearance, and engagement-decline models remain unavailable until genuine historical labels or repeated dated snapshots are collected.
