from __future__ import annotations
import csv, random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SEED=42
BASE_TIME=datetime(2026,1,1,8,0,tzinfo=timezone.utc)
PROVINCES=["Gauteng","Western Cape","KwaZulu-Natal","Eastern Cape"]
DOG_BREEDS=["Labrador","Mixed Breed","Jack Russell","German Shepherd"]
CAT_BREEDS=["Domestic Shorthair","Siamese","Maine Coon","Mixed Breed"]
PLANS=[("ACCIDENT",160.0),("CORE",280.0),("COMPREHENSIVE",430.0)]
CLAIM_TYPES=["ACCIDENT","ILLNESS","ROUTINE_CARE"]

def _write(path:Path,fieldnames:list[str],rows:list[dict])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fieldnames); w.writeheader(); w.writerows(rows)

def generate(output_dir:Path,n_customers:int=500)->dict[str,int]:
    rng=random.Random(SEED); customers=[]; pets=[]; policies=[]; claims=[]; payments=[]
    pet_id=policy_id=claim_id=payment_id=1
    for customer_id in range(1,n_customers+1):
        created=BASE_TIME+timedelta(minutes=customer_id)
        customers.append({"customer_id":customer_id,"first_name":f"Customer{customer_id}","last_name":f"Surname{customer_id}","province":rng.choice(PROVINCES),"created_at":created.isoformat(),"updated_at":created.isoformat(),"is_deleted":False})
        for _ in range(rng.randint(1,2)):
            species=rng.choice(["DOG","CAT"]); breed=rng.choice(DOG_BREEDS if species=="DOG" else CAT_BREEDS)
            dob=date(2017,1,1)+timedelta(days=rng.randint(0,8*365))
            pets.append({"pet_id":pet_id,"customer_id":customer_id,"pet_name":f"Pet{pet_id}","species":species,"breed":breed,"date_of_birth":dob.isoformat(),"created_at":created.isoformat(),"updated_at":created.isoformat(),"is_deleted":False})
            plan_type,base_premium=rng.choice(PLANS); start=date(2025,1,1)+timedelta(days=rng.randint(0,365)); premium=round(base_premium*rng.uniform(.85,1.25),2)
            policies.append({"policy_id":policy_id,"customer_id":customer_id,"pet_id":pet_id,"plan_type":plan_type,"policy_status":"ACTIVE","start_date":start.isoformat(),"end_date":"","monthly_premium":premium,"created_at":created.isoformat(),"updated_at":created.isoformat(),"is_deleted":False})
            for _ in range(rng.randint(0,4)):
                claim_date=start+timedelta(days=rng.randint(1,365)); claim_type=rng.choice(CLAIM_TYPES); amount=round(rng.uniform(350,18000),2)
                status=rng.choices(["SUBMITTED","ASSESSED","APPROVED","REJECTED","PAID"],weights=[10,10,25,10,45],k=1)[0]
                approved=None if status in {"SUBMITTED","ASSESSED","REJECTED"} else round(amount*rng.uniform(.65,1.0),2)
                claim_created=datetime.combine(claim_date,datetime.min.time(),tzinfo=timezone.utc)
                claims.append({"claim_id":claim_id,"policy_id":policy_id,"pet_id":pet_id,"claim_type":claim_type,"claim_status":status,"claim_date":claim_date.isoformat(),"claim_amount":amount,"approved_amount":"" if approved is None else approved,"created_at":claim_created.isoformat(),"updated_at":claim_created.isoformat(),"is_deleted":False})
                if status=="PAID" and approved is not None:
                    payment_date=claim_date+timedelta(days=rng.randint(2,30)); ts=datetime.combine(payment_date,datetime.min.time(),tzinfo=timezone.utc).isoformat()
                    payments.append({"payment_id":payment_id,"claim_id":claim_id,"payment_date":payment_date.isoformat(),"payment_amount":approved,"payment_status":"SETTLED","created_at":ts,"updated_at":ts,"is_deleted":False}); payment_id+=1
                claim_id+=1
            pet_id+=1; policy_id+=1
    datasets={"customers":customers,"pets":pets,"policies":policies,"claims":claims,"claim_payments":payments}
    for name,rows in datasets.items(): _write(output_dir/f"{name}.csv",list(rows[0].keys()) if rows else [],rows)
    return {name:len(rows) for name,rows in datasets.items()}

if __name__=="__main__":
    for table,count in generate(Path("data/generated")).items(): print(f"{table}: {count}")
