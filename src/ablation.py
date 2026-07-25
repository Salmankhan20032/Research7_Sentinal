import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_recall_fscore_support

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('exp', root/'src'/'experiment_final.py')
exp=importlib.util.module_from_spec(spec); spec.loader.exec_module(exp)
d=np.load(root/'results/synthetic_sessions.npz'); X,y=d['X'],d['y']
tr,va,te=exp.split_sessions(y); Xtr=X[tr]; Xte=exp.harden_test(X[te],y[te]); ytr=y[tr]; yte=y[te]
S_tr=exp.summarize(Xtr); S_te=exp.summarize(Xte)
# feature indices in summary vector grouped by original feature and statistic blocks
F=len(exp.FEATURES); D=8*F
all_idx=np.arange(D)
def expanded(orig_idx):
    return np.array([stat*F+i for stat in range(8) for i in orig_idx],dtype=int)
identity=[8,9,10,11]
process=[3,4,12,13]
timing=[5,6,7,14,15]
configs={
 'Full model':all_idx,
 'No identity/context':np.setdiff1d(all_idx,expanded(identity)),
 'No process context':np.setdiff1d(all_idx,expanded(process)),
 'Mean only':np.arange(F),
 'Static extrema only':np.concatenate([np.arange(2*F,4*F)]),
}
rows=[]
for name,idx in configs.items():
    sc=StandardScaler().fit(S_tr[:,idx]); A=sc.transform(S_tr[:,idx]); B=sc.transform(S_te[:,idx])
    m=RandomForestClassifier(n_estimators=120,max_depth=15,min_samples_leaf=3,class_weight='balanced_subsample',random_state=exp.SEED,n_jobs=-1,max_features='sqrt')
    m.fit(A,ytr); p=m.predict(B)
    pr,re,f,_=precision_recall_fscore_support(yte,p,average='macro',zero_division=0)
    rows.append({'configuration':name,'features':len(idx),'accuracy':accuracy_score(yte,p),'balanced_accuracy':balanced_accuracy_score(yte,p),'macro_precision':pr,'macro_recall':re,'macro_f1':f,'fpr':float(np.mean(p[yte==0]!=0))})
out=pd.DataFrame(rows)
out.to_csv(root/'results'/'ablation_metrics.csv',index=False)
fig, ax = plt.subplots(figsize=(7.2, 3.8))
ax.bar(out['configuration'], out['macro_f1'] * 100)
ax.set_ylabel('Macro-F1 (%)')
ax.set_ylim(0, 100)
ax.tick_params(axis='x', rotation=20)
ax.grid(axis='y', alpha=0.25)
fig.tight_layout()
fig.savefig(root/'figures'/'ablation.pdf', bbox_inches='tight')
fig.savefig(root/'figures'/'ablation.png', dpi=220, bbox_inches='tight')
plt.close(fig)
print(out.to_string(index=False))
