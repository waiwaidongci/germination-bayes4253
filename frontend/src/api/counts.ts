import {request} from './client';import {Count,CountBatchPreview,CountBatchLedger} from '../types/domain';
export interface BatchRow{lot_code:string;n:number;k:number}
export interface BatchRequest{study_id:number;source_batch:string;version:number;commit:boolean;rows:BatchRow[]}
export const getCounts=(id:number)=>request<Count[]>(`/studies/${id}/counts`);
export const annotateCount=(id:number,note:string)=>request<Count>(`/counts/${id}`,{method:'PATCH',body:JSON.stringify({note})});
export const previewCountBatch=(id:number,body:Omit<BatchRequest,'study_id'>)=>request<CountBatchPreview>(`/studies/${id}/count-batches`,{method:'POST',body:JSON.stringify({...body,study_id:id})});
export const getCountBatches=(id:number)=>request<CountBatchLedger[]>(`/studies/${id}/count-batches`);
