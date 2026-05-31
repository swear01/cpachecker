# Predicate Set: down

## Status
rescue case

## Bootstrap Predicates
- `(bvsge i (_ bv0 32))`
- `(bvsge n (_ bv0 32))`
- `(bvsge k (_ bv0 32))`
- `(= k i)`
- `(bvsle i n)`
- `(bvsgt k (_ bv0 32))`
- `(= (bvsub n i) (_ bv0 32))`
- `(bvsge (bvsub n i) (_ bv0 32))`

## Count
Bootstrap: 8
B5-MR: see case study
Validator: 0 rejects (post-fix)
Select/store: 0
