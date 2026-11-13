def batch_payload(study,batch='B-202611',version=2,nk=None,commit=False):
    if nk is None:nk=[(100,60+i) for i in range(10)]
    return {'study_id':study.id,'source_batch':batch,'version':version,'commit':commit,
            'rows':[{'lot_code':f'DC-T1-L{i:02}','n':n,'k':k} for i,(n,k) in enumerate(nk,start=1)]}
