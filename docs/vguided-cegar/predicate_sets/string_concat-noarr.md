# Predicate Set: string_concat-noarr

## Status
rescue case

## Bootstrap Predicates
- `(bvsge i (_ bv0 32))`
- `(bvslt i (_ bv100 32))`
- `(bvslt i (_ bv200 32))`
- `(bvsge j (_ bv0 32))`
- `(bvslt j (_ bv100 32))`
- `(= i (bvadd i (_ bv0 32)))`
- `(bvslt (bvadd i j) (_ bv200 32))`
- `(bvsge (bvadd i j) (_ bv0 32))`

## Count
Bootstrap: 8
B5-MR: see case study
Validator: 0 rejects (post-fix)
Select/store: 0
