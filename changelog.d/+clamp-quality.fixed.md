Clamp recomputed quality scores to `[0,1]`; the signed-sigmoid formula could emit values outside the valid range (observed -0.5 to 1.5), which would corrupt ranking and bootstrap filters.
