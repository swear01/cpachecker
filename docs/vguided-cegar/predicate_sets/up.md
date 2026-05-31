# Predicate Set: up

## Status
rescue case

## Bootstrap Predicates
- `(bvsge i (_ bv0 32))`
- `(bvsge k (_ bv0 32))`
- `(bvslt i n)`
- `(= k i)`
- `(bvsge n (_ bv0 32))`
- `(bvsgt k (_ bv0 32))`
- `(bvsle i n)`
- `(= (bvsub k i) (_ bv0 32))`

## Count
Bootstrap: 8
B5-MR: see case study
Validator: 0 rejects (post-fix)
Select/store: 0
