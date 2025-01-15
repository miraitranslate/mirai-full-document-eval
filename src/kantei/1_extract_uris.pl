my %URIs;
for(glob("$ARGV[1]/*.html")){
    open(FH, $_);
    while(<FH>){
        $URIs{$1} = 1 if m#href="(/\d+(_[a-z]+?)?/actions/\d{6}/.+?\.html)"#;
    }
    close(FH);
}
for my $uri (sort keys %URIs){
    print "https://japan.kantei.go.jp$uri\n";
}
