# Modelo 1D de frente, agente de espaldas al obstaculo; politica empuja hacia el obstaculo.
# filtro: v >= -alpha*h + s/k (F1) o v >= -alpha*h (F0) ; ejecutado = k*v con retardo tau, zona muerta 0.03
import numpy as np
def run(D, vo, tau, k=0.4, alpha=2.0, F1=True, dt=0.01, T=30.0, age=0.05, dz=0.03, vmax=0.31, sorpresa=False):
    xo0 = 0.0
    xa = (D - 0.05) + (0.0 if sorpresa else 0.6)   # centro agente; aim = xa+0.05
    cola=[]; v_exec=0.0; dmin=9; t=0
    hist=[]  # (t, xo)
    nd=int(0.1/dt); nt=int(tau/dt); na=int(age/dt)
    cmds=[0.0]*(nt+1)
    xo=xo0; i=0
    while t<T:
        hist.append((t,xo,xa))
        if i % nd == 0:
            # pose medida con antiguedad
            j=max(0,len(hist)-1-na); _,xo_m,xa_m=hist[j]
            j2=max(0,j-int(0.3/dt)); t2,xo2,_=hist[j2]
            vhat = (xo_m-xo2)/max(1e-9,(hist[j][0]-t2)) if j>j2 else 0.0
            h = (xa_m+0.05 - xo_m) - D
            s = max(0.0, vhat) if F1 else 0.0
            lb = -alpha*h + s/k
            v = max(-vmax, lb); v=min(v,vmax)
            cur = k*v
            if abs(cur)<dz: cur=0.0
        cmds.append(cur if i%nd==0 else cmds[-1])
        v_exec = cmds[-1-nt]
        xa += v_exec*dt; xo += vo*dt
        dmin=min(dmin, xa-xo); t+=dt; i+=1
    return dmin
for D in (0.255,0.33,0.35):
  for F1 in (False,True):
    row=[]
    for tau in (0.45,0.85):
      for vo in (0.03,0.05,0.07):
        row.append(f"{run(D,vo,tau,F1=F1):.3f}")
    print(D, "F1" if F1 else "F0", row)
print("sorpresa D=0.33 F1", [f"{run(0.33,0.05,t,sorpresa=True):.3f}" for t in (0.45,0.85)])
