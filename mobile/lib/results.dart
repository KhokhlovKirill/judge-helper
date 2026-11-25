List<dynamic> sortedResults(List<dynamic> results,int category,String column,bool ascending) {
  final selected=results.where((r)=>r['category']==category).toList();
  selected.sort((a,b)=>(ascending?1:-1)*(a[column] as Comparable).compareTo(b[column]));
  return selected;
}
