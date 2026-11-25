import 'package:flutter_test/flutter_test.dart';
import 'package:judge_helper/results.dart';

void main(){
  test('Сортировка по всем шести столбцам в обе стороны сохраняет места',(){
    final rows=[{'rank':1,'name':'Б','club':'Б','technique':9,'artistry':9,'total':9,'category':1},{'rank':2,'name':'А','club':'А','technique':7,'artistry':7,'total':7,'category':1},{'rank':1,'category':2}];
    for(final key in ['rank','name','club','technique','artistry','total']){
      final asc=sortedResults(rows,1,key,true);
      final desc=sortedResults(rows,1,key,false);
      expect(asc.length,2);expect(desc,asc.reversed.toList());
      expect((asc.first[key] as Comparable).compareTo(asc.last[key]),lessThan(0));
      expect(rows.first['rank'],1);
    }
  });
}
